"""스케줄 진입점. 모든 시각은 KST. 각 작업은 여러 번 돌려도 안전하다(멱등).

| 시각            | 작업                                                    |
| 15분마다        | 1~3단계 수집·중복 제거·묶기                             |
| 매시 정각       | 4단계 생성 대상 선정 → 배치 제출                        |
| 매시 30분       | 완료된 배치 회수 → 6단계 검증 → drafts(베타)/posts(출시) |
| 03:00           | 원문 본문 30일 경과분 비우기, 사용량 집계 (백업은 infra/backup.sh) |
| 04:30           | 쟁점 정리 1편 선정·즉시 생성                            |
| 06:20           | 베타: 손대지 않은 초안 자동 게시                        |
| 06:25           | 1면 선정 (전 사용자 공통)                               |
| 06:30           | 이메일 수신자 전원의 조간 사전 조립 → editions          |
| 07:00~10:50     | 10분마다 설정 시각별 이메일 발송, 실패분은 10분 뒤 1회 재시도 |
| 일요일 22:00    | 교양 7편 배치 생성, 주간 품질 리포트                    |
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta

import psycopg

from ..db import log_decision
from ..editor import assemble as editor
from ..editor.front_page import select_front
from ..generate import batch
from ..generate.gateway import AnthropicLLM, LLMClient, budget_state
from ..mail.render import render_edition
from ..mail.sender import get_sender, send_login_link
from ..ops import alerts, maintenance, reports
from ..pipeline import auto_publish_pending, process_received, publish_draft, reject_draft
from ..process import cluster as clustering
from ..process.embed import get_embedder
from ..process.ingest import ingest_article
from ..process.select import expire_stale, select_targets
from ..publish import triggers
from ..publish.commit import publish_correction
from ..settings import Settings
from ..timeutil import kst, kst_today

log = logging.getLogger(__name__)
_llm: LLMClient | None = None


def get_llm() -> LLMClient | None:
    """API 키가 없으면 None: 생성만 멈추고 선정·대기열은 계속 쌓인다."""
    global _llm
    if _llm is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return None
        _llm = AnthropicLLM()
    return _llm


def set_llm(llm: LLMClient | None) -> None:
    global _llm
    _llm = llm


# ── 15분마다 ──────────────────────────────────────────

def collect(conn: psycopg.Connection, s: Settings, now: datetime) -> dict:
    from ..collect.feeds import Collector

    emb = get_embedder()
    llm = get_llm()
    gray = None
    if s["cluster"].get("gray_llm") and llm is not None:
        from ..verify.runner import make_gray_judge

        gray = make_gray_judge(conn, llm, s)

    def ingest(**kw):
        return ingest_article(conn, s, emb, gray_judge=gray, **kw)

    stats = Collector(conn, s, ingest).run()
    stats["closed"] = clustering.close_stale(conn, now, s)
    conn.commit()
    last = conn.execute("SELECT max(fetched_at) AS t FROM raw_articles").fetchone()["t"]
    if last is None or now - last > timedelta(hours=1):
        alerts.alert(conn, "collect_zero", kst(now).strftime("%Y-%m-%dT%H"),
                     f"수집 1시간 연속 0건 (마지막 수집: {kst(last).strftime('%m-%d %H:%M') if last else '없음'})")
    return stats


# ── 매시 정각 / 30분 ──────────────────────────────────

def _check_budget(conn: psycopg.Connection, s: Settings, now: datetime) -> None:
    b = budget_state(conn, s)
    if b.ratio >= s["budget"]["alert_ratio"]:
        alerts.alert(conn, "budget_80", kst(now).strftime("%Y-%m"),
                     f"LLM 당월 비용 ${b.spent:.2f} / 상한 ${b.limit:.0f} ({b.ratio:.0%})"
                     + (" — 생성 제출 중단" if b.blocked else ""))


def hourly_select(conn: psycopg.Connection, s: Settings, now: datetime) -> dict:
    out = {"expired": expire_stale(conn, now, s), "selected": select_targets(conn, now, s)}
    conn.commit()
    llm = get_llm()
    if llm is None:
        out["note"] = "ANTHROPIC_API_KEY 없음: 제출하지 않고 대기열에 쌓음"
        return out
    _check_budget(conn, s, now)
    out["submit"] = batch.submit_pending(conn, llm, s, now)
    out["verify"] = process_received(conn, s, get_embedder(), llm, now)
    return out


def hourly_collect(conn: psycopg.Connection, s: Settings, now: datetime) -> dict:
    llm = get_llm()
    out: dict = {}
    if llm is not None:
        out["batches"] = batch.collect_batches(conn, llm, s, now)
    out["verify"] = process_received(conn, s, get_embedder(), llm, now)
    out["explainers"] = triggers.scan_explainers(conn, now, s)
    conn.commit()
    if llm is not None:
        _check_budget(conn, s, now)
        # 즉시 호출 대상(1면 후보 재생성, 해설)은 다음 정각을 기다리지 않는다
        out["immediate"] = batch.submit_pending(conn, llm, s, now, immediate_only=True)
        out["verify2"] = process_received(conn, s, get_embedder(), llm, now)
    return out


def issue_select(conn: psycopg.Connection, s: Settings, now: datetime) -> dict:
    rid = triggers.select_issue(conn, now, s)
    conn.commit()
    out: dict = {"issue_request": rid}
    llm = get_llm()
    if rid and llm is not None:
        out["submit"] = batch.submit_pending(conn, llm, s, now, kinds=("issue",), immediate_only=True)
        out["verify"] = process_received(conn, s, get_embedder(), llm, now)
        # 재생성이 필요하면 바로 한 번 더
        out["submit2"] = batch.submit_pending(conn, llm, s, now, kinds=("issue",), immediate_only=True)
        out["verify2"] = process_received(conn, s, get_embedder(), llm, now)
    return out


# ── 아침 06:00~07:00 ──────────────────────────────────

def auto_publish(conn: psycopg.Connection, s: Settings, now: datetime) -> dict:
    if not s["review"]["enabled"]:
        return {"skipped": "review disabled"}
    return {"published": auto_publish_pending(conn, s, get_embedder(), now)}


def front(conn: psycopg.Connection, s: Settings, now: datetime) -> dict:
    d = kst_today(now)
    row = select_front(conn, d, now, s)
    conn.commit()
    if len(row["seqs"]) < s["front"]["n"] or row["fallback"]:
        alerts.alert(conn, "front_short", str(d), f"{d} 1면 후보 {len(row['seqs'])}편 (전날 종합으로 채움: {row['fallback']})")
    return {"seqs": row["seqs"], "fallback": row["fallback"], "issue_seq": row["issue_seq"]}


def email_recipients(conn: psycopg.Connection) -> list[dict]:
    return conn.execute(
        """SELECT u.id, u.email, COALESCE(p.delivery_hour, 7) AS delivery_hour
           FROM users u LEFT JOIN user_prefs p ON p.user_id = u.id
           WHERE u.deleted_at IS NULL AND COALESCE(p.email_enabled, true)
             AND NOT EXISTS (SELECT 1 FROM email_suppressions s WHERE s.email = u.email)
           ORDER BY u.created_at, u.id"""
    ).fetchall()


def assemble_morning(conn: psycopg.Connection, s: Settings, now: datetime) -> dict:
    """사용자 단위로 격리한다. 한 명 실패가 다른 사람을 막지 않는다."""
    d = kst_today(now)
    as_of = editor.current_max_seq(conn)
    ok, failed = 0, []
    for u in email_recipients(conn):
        try:
            with conn.transaction():
                eid = editor.assemble_and_save(conn, str(u["id"]), now, s, as_of_seq=as_of)
                conn.execute(
                    """INSERT INTO email_sends (edition_id, user_id, edition_date, scheduled_hour)
                       VALUES (%s, %s, %s, %s) ON CONFLICT (user_id, edition_date) DO NOTHING""",
                    (eid, u["id"], d, u["delivery_hour"]),
                )
            ok += 1
        except Exception as e:  # noqa: BLE001
            log.exception("assemble failed for %s", u["id"])
            failed.append({"user": str(u["id"]), "error": str(e)[:200]})
    conn.commit()
    if failed:
        log_decision(conn, "assemble", f"date:{d}", {"ok": ok, "failed": failed[:50]})
        conn.commit()
        alerts.alert(conn, "assemble_failed", str(d), f"{d} 조간 조립 실패 {len(failed)}명 / 성공 {ok}명")
    return {"as_of_seq": as_of, "ok": ok, "failed": len(failed)}


def send_emails(conn: psycopg.Connection, s: Settings, now: datetime) -> dict:
    """조립이 끝난 editions만 발송한다. SES 실패분은 10분 뒤 1회 재시도."""
    d = kst_today(now)
    hour = kst(now).hour
    due = conn.execute(
        """SELECT s.*, u.email FROM email_sends s JOIN users u ON u.id = s.user_id
           WHERE s.edition_date = %s AND s.status = 'queued' AND s.scheduled_hour <= %s
             AND (s.next_attempt_at IS NULL OR s.next_attempt_at <= %s)
           ORDER BY s.scheduled_hour, s.id""",
        (d, hour, now),
    ).fetchall()
    sender = get_sender(s["email"]["from"])
    sent = failed = suppressed = 0
    for row in due:
        if conn.execute("SELECT 1 FROM email_suppressions WHERE email = %s", (row["email"],)).fetchone():
            conn.execute("UPDATE email_sends SET status='suppressed' WHERE id=%s", (row["id"],))
            suppressed += 1
            continue
        # 설정 변경으로 재조립됐으면 최신 지면을 보낸다 (웹과 이메일이 같은 지면)
        eid = conn.execute(
            "SELECT id FROM editions WHERE user_id = %s AND edition_date = %s ORDER BY id DESC LIMIT 1",
            (row["user_id"], d),
        ).fetchone()["id"]
        try:
            mid = sender.send(row["email"], render_edition(conn, eid))
            conn.execute(
                "UPDATE email_sends SET status='sent', edition_id=%s, message_id=%s, sent_at=%s, attempts=attempts+1 WHERE id=%s",
                (eid, mid, now, row["id"]))
            sent += 1
        except Exception as e:  # noqa: BLE001
            attempts = row["attempts"] + 1
            status = "failed" if attempts >= 2 else "queued"
            conn.execute(
                "UPDATE email_sends SET status=%s, attempts=%s, last_error=%s, next_attempt_at=%s WHERE id=%s",
                (status, attempts, str(e)[:500], now + timedelta(minutes=s["email"]["retry_minutes"]), row["id"]),
            )
            failed += 1
        conn.commit()
    if hasattr(sender, "close"):
        sender.close()
    return {"sent": sent, "failed": failed, "suppressed": suppressed}


# ── 정비·주간 ─────────────────────────────────────────

def maintenance_daily(conn: psycopg.Connection, s: Settings, now: datetime) -> dict:
    return maintenance.run(conn, now)


def culture_week(conn: psycopg.Connection, s: Settings, now: datetime) -> dict:
    created = triggers.schedule_culture_week(conn, now, s)
    conn.commit()
    out: dict = {"culture_requests": created, "weekly_report": str(reports.weekly_quality(conn, now))}
    llm = get_llm()
    if llm is not None and created:
        out["submit"] = batch.submit_pending(conn, llm, s, now, kinds=("culture",))
    return out


# ── 작업 큐 (웹이 넣는 요청) ─────────────────────────

def handle_job(conn: psycopg.Connection, s: Settings, job: dict, now: datetime) -> dict:
    t, p = job["type"], job["payload"]
    if t == "assemble_edition":
        eid = editor.assemble_and_save(conn, p["user_id"], now, s)
        conn.commit()
        return {"edition_id": eid}
    if t == "publish_draft":
        return {"seq": publish_draft(conn, s, get_embedder(), int(p["draft_id"]), now, p.get("decision", "approved"))}
    if t == "reject_draft":
        reject_draft(conn, int(p["draft_id"]), p["reason"], p.get("note"), now)
        return {"rejected": p["draft_id"]}
    if t == "publish_correction":
        with conn.transaction():
            seq = publish_correction(conn, get_embedder(), target_seq=int(p["target_seq"]), title=p["title"],
                                     summary=p["summary"], body=p["body"], author=p.get("author", "founder"), now=now)
            if p.get("report_id"):
                conn.execute("UPDATE error_reports SET correction_seq=%s, status='confirmed', answered_at=%s WHERE id=%s",
                             (seq, now, int(p["report_id"])))
            triggers.after_publish(conn, seq, now, s)
        conn.commit()
        return {"seq": seq}
    if t == "send_login_email":
        return {"message_id": send_login_link(get_sender(s["email"]["from"]), p["email"], p["url"])}
    raise ValueError(f"unknown job type {t}")
