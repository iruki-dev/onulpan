from datetime import timedelta

from worker.editor.assemble import PRESETS, assemble_edition, save_edition
from worker.editor.front_page import select_front
from worker.publish import triggers
from worker.timeutil import kst_today

from helpers import full_day


def _user(conn, email="u@x.kr", preset="standard", weights=None, plan="free", niche=None):
    uid = conn.execute("INSERT INTO users (email, provider, plan) VALUES (%s,'email',%s) RETURNING id",
                       (email, plan)).fetchone()["id"]
    import json
    conn.execute("INSERT INTO user_prefs (user_id, preset, section_weights, niche_topics) VALUES (%s,%s,%s,%s)",
                 (uid, preset, json.dumps(weights or {}), niche or []))
    conn.commit()
    return str(uid)


def _max_seq(conn):
    return conn.execute("SELECT max(seq) AS m FROM posts").fetchone()["m"]


def test_front_is_logged_and_shared(conn, s, now):
    full_day(conn, s, now)
    row = select_front(conn, kst_today(now), now, s)
    assert len(row["seqs"]) == 3
    log = conn.execute("SELECT payload FROM decision_log WHERE kind='select'").fetchone()["payload"]
    assert len(log["top"]) == 5 and log["top"][0]["picked"]
    sections = [conn.execute("SELECT section FROM posts WHERE seq=%s", (q,)).fetchone()["section"] for q in row["seqs"]]
    assert max(sections.count(x) for x in sections) <= 2
    a, b = _user(conn, "a@x.kr"), _user(conn, "b@x.kr", "long")
    ea = assemble_edition(conn, a, _max_seq(conn), now, s)
    eb = assemble_edition(conn, b, _max_seq(conn), now, s)
    assert [p["seq"] for p in ea.front] == [p["seq"] for p in eb.front] == row["seqs"]


def test_deterministic(conn, s, now):
    full_day(conn, s, now)
    u = _user(conn)
    one = assemble_edition(conn, u, _max_seq(conn), now, s).slots()
    two = assemble_edition(conn, u, _max_seq(conn), now, s).slots()
    assert one == two


def test_presets_and_budget(conn, s, now):
    full_day(conn, s, now)
    short = assemble_edition(conn, _user(conn, "s@x.kr", "short"), _max_seq(conn), now, s)
    std = assemble_edition(conn, _user(conn, "t@x.kr", "standard"), _max_seq(conn), now, s)
    assert len(short.front) == 2 and not short.issue and not short.culture
    assert len(std.front) == 3 and std.issue == []  # 이 픽스처 날에는 쟁점 정리 글이 없다
    for ed in (short, std):
        chars = sum(p["char_count"] for p in ed.front + ed.sections)
        assert chars <= PRESETS[ed.preset].budget_chars
        seqs = [x["seq"] for x in ed.slots() if "seq" in x]
        assert len(seqs) == len(set(seqs))
        slugs = [p["slug"] for p in ed.front + ed.sections]
        assert len(slugs) == len(set(slugs))  # slug당 1편


def test_section_floor_and_weights(conn, s, now):
    full_day(conn, s, now)
    ed = assemble_edition(conn, _user(conn, weights={"world": 0.7, "scitech": 1.3}), _max_seq(conn), now, s)
    present = {p["section"] for p in ed.front + ed.sections}
    assert {"politics", "economy", "society", "world", "scitech"} <= present


def test_cursor_excludes_already_read(conn, s, now):
    full_day(conn, s, now)
    u = _user(conn)
    first_max = _max_seq(conn)
    conn.execute("INSERT INTO reading_cursors (user_id, last_seq, updated_at) VALUES (%s,%s,%s)", (u, first_max, now))
    conn.execute("INSERT INTO slugs VALUES ('새-소식','새 소식')")
    new_seq = conn.execute(
        """INSERT INTO posts (kind, section, slug, title, summary, body_md, char_count, model, prompt_version, verify_report,
                              cost_usd, importance, created_at)
           VALUES ('fact','world','새-소식','새 소식','요약','본문',450,'m','v','{}',0,1,%s) RETURNING seq""",
        (now + timedelta(hours=1),)).fetchone()["seq"]
    conn.commit()
    ed = assemble_edition(conn, u, new_seq, now + timedelta(hours=2), s)
    assert [p["seq"] for p in ed.sections] == [new_seq]  # 이미 연 조간의 글은 다시 싣지 않는다
    assert ed.briefs == []


def test_collection_delay_fallback(conn, s, now):
    full_day(conn, s, now)
    u = _user(conn)
    later = now + timedelta(hours=50)
    ed = assemble_edition(conn, u, _max_seq(conn), later, s)
    assert "collection_delayed" in ed.notices
    assert ed.sections  # 72시간 창으로 넓혀 채운다


def test_catchup_for_absent_readers(conn, s, now):
    full_day(conn, s, now)
    u = _user(conn)
    conn.execute("INSERT INTO reading_cursors (user_id, last_seq, updated_at) VALUES (%s, 0, %s)",
                 (u, now - timedelta(days=4)))
    seq = conn.execute(
        """INSERT INTO posts (kind, section, slug, title, summary, body_md, char_count, model, prompt_version, verify_report,
                              cost_usd, importance) VALUES ('synthesis','economy','누리전자-실적','종합','요약','본문',500,'m','v','{}',0,3)
           RETURNING seq""").fetchone()["seq"]
    conn.commit()
    ed = assemble_edition(conn, u, seq, now, s)
    assert [p["seq"] for p in ed.catchup] == [seq]


def test_niche_topics_for_paid_users(conn, s, now):
    full_day(conn, s, now)
    slug = conn.execute("SELECT slug FROM posts WHERE section='world' LIMIT 1").fetchone()["slug"]
    free = assemble_edition(conn, _user(conn, "f@x.kr", niche=[slug]), _max_seq(conn), now, s)
    paid = assemble_edition(conn, _user(conn, "p@x.kr", plan="founding", niche=[slug]), _max_seq(conn), now, s)
    assert not free.niche_seqs
    assert paid.niche_seqs and any(x.get("niche") for x in paid.slots())


def test_novelty_demotes_recent_slugs(conn, s, now):
    full_day(conn, s, now)
    u = _user(conn)
    ed = assemble_edition(conn, u, _max_seq(conn), now, s)
    save_edition(conn, ed)
    conn.commit()
    from worker.editor.assemble import recent_slugs

    assert recent_slugs(conn, u, kst_today(now) + timedelta(days=1), 3) == {p["slug"] for p in ed.front + ed.sections + ed.issue}


def test_culture_slot(conn, s, now):
    full_day(conn, s, now)
    topics = triggers.culture_topics(kst_today(now), 7)
    assert topics == triggers.culture_topics(kst_today(now), 7)  # 날짜로 결정된다
    assert len({t["date"] for t in topics}) == 7


def test_reassembly_after_reading_keeps_sections(conn, s, now):
    """설정 변경으로 같은 날 다시 조립해도, 오늘 지면을 연 뒤 앞선 커서 때문에 지면이 비지 않는다."""
    full_day(conn, s, now)
    u = _user(conn)
    first = assemble_edition(conn, u, _max_seq(conn), now, s)
    save_edition(conn, first)
    conn.execute("INSERT INTO reading_cursors (user_id, last_seq, updated_at) VALUES (%s,%s,%s)", (u, first.as_of_seq, now))
    conn.execute("UPDATE user_prefs SET preset = 'short' WHERE user_id = %s", (u,))
    conn.commit()
    again = assemble_edition(conn, u, first.as_of_seq, now + timedelta(minutes=5), s)
    assert again.sections, again.slots()
    assert len(again.front) == 2
