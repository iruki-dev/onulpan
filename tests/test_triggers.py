from datetime import timedelta

from worker.dev.fake import FakeLLM
from worker.generate import batch
from worker.pipeline import auto_publish_pending, process_received
from worker.publish import triggers

from helpers import full_day


def _fact(conn, slug, n, now):
    seqs = []
    for i in range(n):
        seqs.append(conn.execute(
            """INSERT INTO posts (kind, section, slug, title, summary, body_md, char_count, model, prompt_version,
                                  verify_report, cost_usd, created_at)
               VALUES ('fact','economy',%s,%s,'요약','본문입니다. 숫자는 없다.',10,'m','v','{}',0,%s) RETURNING seq""",
            (slug, f"글 {i}", now)).fetchone()["seq"])
    return seqs


def test_synthesis_after_three_facts(conn, s, now):
    conn.execute("INSERT INTO slugs VALUES ('주제','주제')")
    seqs = _fact(conn, "주제", 2, now)
    assert triggers.after_publish(conn, seqs[-1], now, s) == []
    seqs = _fact(conn, "주제", 1, now)
    assert len(triggers.after_publish(conn, seqs[-1], now, s)) == 1
    more = _fact(conn, "주제", 3, now)
    assert triggers.after_publish(conn, more[-1], now, s) == []  # slug당 하루 1편


def test_synthesis_after_seven_days(conn, s, now):
    conn.execute("INSERT INTO slugs VALUES ('오래','오래')")
    seqs = _fact(conn, "오래", 1, now - timedelta(days=8))
    assert len(triggers.after_publish(conn, seqs[-1], now, s)) == 1


def test_explainer_trigger_and_cap(conn, s, now):
    conn.execute("INSERT INTO slugs VALUES ('주제','주제')")
    seqs = _fact(conn, "주제", 3, now)
    for t in ["기준금리", "환율", "물가", "관세"]:
        for q in seqs:
            conn.execute("INSERT INTO term_mentions VALUES (%s, %s)", (t, q))
    created = triggers.scan_explainers(conn, now, s)
    assert len(created) == 3  # 베타 하루 상한
    assert triggers.scan_explainers(conn, now, s) == []


def test_issue_selected_for_disputed_multi_group(conn, s, now):
    events, emb, llm = full_day(conn, s, now)
    rid = triggers.select_issue(conn, now, s)
    assert rid is not None
    assert triggers.select_issue(conn, now, s) is None  # 하루 1편
    batch.submit_pending(conn, llm, s, now)
    process_received(conn, s, emb, llm, now)
    auto_publish_pending(conn, s, emb, now)
    issue = conn.execute("SELECT * FROM posts WHERE kind = 'issue'").fetchone()
    assert issue and len(issue["meta"]["sections"]["positions"]) == 2
    assert conn.execute("SELECT count(*) AS n FROM post_links WHERE from_seq=%s AND rel='follows'",
                        (issue["seq"],)).fetchone()["n"] == 1


def test_synthesis_generation_end_to_end(conn, s, now):
    events, emb, llm = full_day(conn, s, now)
    s["verify"]["lengths"]["body"]["synthesis"] = [300, 1200]  # 가짜 LLM의 추출식 종합은 짧다
    slug = conn.execute("SELECT slug FROM posts WHERE title LIKE '누리전자%'").fetchone()["slug"]
    conn.execute(
        """INSERT INTO posts (kind, section, slug, title, summary, body_md, char_count, model, prompt_version, verify_report,
                              cost_usd, created_at)
           SELECT 'fact', section, slug, title || ' 후속', summary, body_md, char_count, model, prompt_version, verify_report,
                  cost_usd, created_at FROM posts WHERE slug = %s""", (slug,))
    conn.execute(
        """INSERT INTO post_sources SELECT p2.seq, s.raw_article_id, s.outlet_id, s.url, s.title
           FROM posts p2 JOIN posts p1 ON p1.slug = p2.slug AND p1.title || ' 후속' = p2.title
           JOIN post_sources s ON s.post_seq = p1.seq""")
    triggers.maybe_synthesis(conn, slug, now, s)
    conn.execute("INSERT INTO posts (kind, section, slug, title, summary, body_md, char_count, model, prompt_version, "
                 "verify_report, cost_usd) SELECT kind, section, slug, title || ' 2', summary, body_md, char_count, model, "
                 "prompt_version, verify_report, cost_usd FROM posts WHERE slug = %s AND title LIKE '%%후속' LIMIT 1", (slug,))
    conn.commit()
    assert triggers.maybe_synthesis(conn, slug, now, s) is not None
    conn.commit()
    batch.submit_pending(conn, llm, s, now)
    batch.collect_batches(conn, llm, s, now)
    process_received(conn, s, emb, llm, now)
    auto_publish_pending(conn, s, emb, now)
    syn = conn.execute("SELECT * FROM posts WHERE kind='synthesis'").fetchone()
    assert syn is not None, conn.execute("SELECT verify_report FROM generation_requests WHERE kind='synthesis'").fetchall()
    rels = {r["rel"] for r in conn.execute("SELECT rel FROM post_links WHERE from_seq=%s", (syn["seq"],)).fetchall()}
    assert "summarizes" in rels
