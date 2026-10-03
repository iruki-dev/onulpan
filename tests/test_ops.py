import email
from datetime import timedelta
from pathlib import Path

from worker.collect.feeds import parse_feed
from worker.collect.policy_api import parse_policy_xml
from worker.collect.urls import normalize_url
from worker.editor.assemble import assemble_and_save
from worker.editor.front_page import select_front
from worker.jobs import queue, tasks
from worker.mail import tokens
from worker.mail.render import render_edition
from worker.ops import maintenance
from worker.publish.commit import publish_correction
from worker.timeutil import kst_today

from helpers import full_day


def test_url_normalization():
    a = normalize_url("http://m.example.co.kr/news/1/?utm_source=rss&id=3&fbclid=x")
    b = normalize_url("https://www.example.co.kr/news/1?id=3")
    assert a == b


def test_parse_feed():
    xml = b"""<?xml version="1.0"?><rss><channel><item><title>T</title><link>https://a.kr/1</link>
    <pubDate>Mon, 05 Oct 2026 09:00:00 +0900</pubDate></item></channel></rss>"""
    items = parse_feed(xml)
    assert items[0].url == "https://a.kr/1" and items[0].published_at.hour == 0


def test_parse_policy_api():
    xml = """<response><body><NewsItem><Title>정책</Title><OriginalUrl>https://korea.kr/1</OriginalUrl>
    <DataContents>&lt;p&gt;본문&lt;/p&gt;</DataContents><ApproveDate>10/05/2026 09:00:00</ApproveDate></NewsItem></body></response>"""
    items = parse_policy_xml(xml)
    assert items[0].title == "정책" and items[0].body == "본문"


def test_unsubscribe_token():
    t = tokens.sign("unsub", "abc")
    assert tokens.verify("unsub", t) == "abc"
    assert tokens.verify("unsub", t[:-1] + ("0" if t[-1] != "0" else "1")) is None


def test_email_render_and_send(conn, s, now, tmp_path, monkeypatch):
    full_day(conn, s, now)
    uid = conn.execute("INSERT INTO users (email, provider) VALUES ('r@x.kr','email') RETURNING id").fetchone()["id"]
    conn.commit()
    out = tasks.assemble_morning(conn, s, now)
    assert out["ok"] == 1 and out["failed"] == 0
    eid = conn.execute("SELECT id FROM editions WHERE user_id=%s", (uid,)).fetchone()["id"]
    mail = render_edition(conn, eid)
    assert "오늘판" in mail.subject and "1면" in mail.html and "수신 거부" in mail.html
    monkeypatch.setattr("worker.mail.sender.ROOT", tmp_path)
    res = tasks.send_emails(conn, s, now + timedelta(hours=1))
    assert res["sent"] == 1
    eml = next((tmp_path / "var" / "outbox").glob("*.eml"))
    msg = email.message_from_bytes(eml.read_bytes())
    assert msg["List-Unsubscribe"].startswith("<http")
    assert tasks.send_emails(conn, s, now + timedelta(hours=1))["sent"] == 0  # 한 번만


def test_email_retry_once(conn, s, now, monkeypatch):
    full_day(conn, s, now)
    conn.execute("INSERT INTO users (email, provider) VALUES ('r@x.kr','email')")
    conn.commit()
    tasks.assemble_morning(conn, s, now)

    class Boom:
        def send(self, to, mail):
            raise RuntimeError("SES down")

    monkeypatch.setattr(tasks, "get_sender", lambda _: Boom())
    t = now + timedelta(hours=1)
    assert tasks.send_emails(conn, s, t)["failed"] == 1
    assert tasks.send_emails(conn, s, t + timedelta(minutes=5))["failed"] == 0  # 10분 전에는 다시 안 보냄
    assert tasks.send_emails(conn, s, t + timedelta(minutes=10))["failed"] == 1
    row = conn.execute("SELECT status, attempts FROM email_sends").fetchone()
    assert row["status"] == "failed" and row["attempts"] == 2


def test_suppressed_and_disabled_not_assembled(conn, s, now):
    full_day(conn, s, now)
    conn.execute("INSERT INTO users (email, provider) VALUES ('a@x.kr','email'), ('b@x.kr','email')")
    conn.execute("INSERT INTO email_suppressions (email, reason) VALUES ('b@x.kr','bounce')")
    conn.commit()
    assert tasks.assemble_morning(conn, s, now)["ok"] == 1


def test_job_queue_reassembles(conn, s, now):
    full_day(conn, s, now)
    uid = str(conn.execute("INSERT INTO users (email, provider) VALUES ('q@x.kr','email') RETURNING id").fetchone()["id"])
    first = assemble_and_save(conn, uid, now, s)
    queue.enqueue(conn, "assemble_edition", {"user_id": uid})
    conn.commit()
    assert queue.run_once(conn, s, tasks.handle_job)
    rows = conn.execute("SELECT id, as_of_seq FROM editions WHERE user_id=%s ORDER BY id", (uid,)).fetchall()
    assert len(rows) == 2 and rows[0]["as_of_seq"] == rows[1]["as_of_seq"] and rows[0]["id"] == first
    assert conn.execute("SELECT status FROM jobs").fetchone()["status"] == "done"


def test_failing_job_retries_then_fails(conn, s, now):
    queue.enqueue(conn, "nope", {})
    conn.commit()
    for _ in range(3):
        conn.execute("UPDATE jobs SET run_after = now() - interval '1 second'")
        conn.commit()
        queue.run_once(conn, s, tasks.handle_job)
    assert conn.execute("SELECT status FROM jobs").fetchone()["status"] == "failed"


def test_correction_is_a_new_post(conn, s, now):
    events, emb, _ = full_day(conn, s, now)
    target = conn.execute("SELECT seq FROM posts ORDER BY seq LIMIT 1").fetchone()["seq"]
    seq = publish_correction(conn, emb, target_seq=target, title="정정: 숫자 바로잡음", summary="요약",
                             body="원래 글의 숫자가 틀렸습니다.\n\n바른 숫자는 이렇습니다.", author="founder", now=now)
    conn.commit()
    link = conn.execute("SELECT * FROM post_links WHERE from_seq=%s", (seq,)).fetchone()
    assert link["to_seq"] == target and link["rel"] == "corrects"
    assert conn.execute("SELECT count(*) AS n FROM post_sources WHERE post_seq=%s", (seq,)).fetchone()["n"] >= 2
    # 정정된 글은 1면 후보에서 빠진다
    row = select_front(conn, kst_today(now), now, s)
    assert target not in row["seqs"]


def test_purge_bodies(conn, s, now):
    full_day(conn, s, now)
    n = maintenance.purge_bodies(conn, now + timedelta(days=31))
    assert n == 15
    assert conn.execute("SELECT count(*) AS n FROM raw_articles WHERE body IS NOT NULL").fetchone()["n"] == 0
    assert conn.execute("SELECT count(*) AS n FROM post_sources").fetchone()["n"] > 0  # 출처는 남는다


def test_reports(conn, s, now, monkeypatch, tmp_path):
    full_day(conn, s, now)
    from worker.ops import reports

    monkeypatch.setattr(reports, "REPORTS", tmp_path)
    p = reports.weekly_quality(conn, now + timedelta(days=1))
    assert "검증 통과율" in Path(p).read_text()
    assert "선결제 전환율" in Path(reports.twelve_week(conn, now)).read_text()


def test_alert_sent_once(conn):
    from worker.ops import alerts

    assert alerts.alert(conn, "budget_80", "2026-10", "x") is True
    assert alerts.alert(conn, "budget_80", "2026-10", "x") is False
