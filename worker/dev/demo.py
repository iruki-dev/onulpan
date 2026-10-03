"""개발용 시드: 가상 매체·기사로 수집 → 묶기 → 생성(가짜 LLM) → 검증 → 게시 → 1면 → 조간까지 한 번 돌린다.

    python -m worker.jobs.cli seed-demo

운영 DB에서 돌리지 않도록 ONULPAN_ENV=production이면 거부한다.
"""
from __future__ import annotations

import os
from datetime import timedelta

import psycopg

from ..editor.assemble import assemble_and_save
from ..editor.front_page import select_front
from ..generate import batch
from ..pipeline import auto_publish_pending, process_received
from ..process.embed import set_embedder
from ..process.ingest import ingest_article
from ..process.select import select_targets
from ..publish import triggers
from ..settings import Settings
from ..timeutil import kst_today, now as utcnow
from .fake import FakeLLM, KeywordEmbedder, article_times, build_events, load_fixture

DEMO_USERS = [
    ("demo@onulpan.local", "standard", {}),
    ("short@onulpan.local", "short", {"economy": 1.3}),
    ("long@onulpan.local", "long", {"politics": 0.7, "scitech": 1.3}),
]


def ensure_outlets(conn: psycopg.Connection) -> dict[str, int]:
    out = {}
    for o in load_fixture()["outlets"]:
        row = conn.execute(
            """INSERT INTO outlets (name, domain, feed_url, feed_type, grp, active)
               VALUES (%s, %s, NULL, 'rss', %s, false)
               ON CONFLICT (domain) DO UPDATE SET name = EXCLUDED.name RETURNING id""",
            (o["name"], o["domain"], o["grp"]),
        ).fetchone()
        out[o["name"]] = row["id"]
    return out


def seed(conn: psycopg.Connection, s: Settings, now=None, llm: FakeLLM | None = None) -> dict:
    if os.environ.get("ONULPAN_ENV") == "production":
        raise RuntimeError("seed-demo는 운영 환경에서 돌리지 않는다")
    now = now or utcnow()
    events = build_events(now - timedelta(hours=4))
    emb = KeywordEmbedder([e["key"] for e in events])
    set_embedder(emb)
    llm = llm or FakeLLM(events)
    outlets = ensure_outlets(conn)

    ingested = 0
    for ev in events:
        for a in ev["articles"]:
            slug = abs(hash((ev["key"], a["outlet"], a["title"]))) % 10**8
            if ingest_article(conn, s, emb, outlet_id=outlets[a["outlet"]],
                              url=f"https://{a['outlet']}.demo.invalid/news/{slug}", title=a["title"],
                              body=a["body"], published_at=article_times(now, a["hours_ago"])):
                ingested += 1
    conn.commit()

    selected = select_targets(conn, now, s)
    conn.commit()
    stats = {"ingested": ingested, "selected": len(selected)}
    stats["submit"] = batch.submit_pending(conn, llm, s, now)
    stats["collect"] = batch.collect_batches(conn, llm, s, now)
    stats["verify"] = process_received(conn, s, emb, llm, now)
    # 재생성 한 바퀴
    batch.submit_pending(conn, llm, s, now)
    batch.collect_batches(conn, llm, s, now)
    process_received(conn, s, emb, llm, now)
    if s["review"]["enabled"]:
        stats["auto_published"] = len(auto_publish_pending(conn, s, emb, now))

    # 쟁점 정리 + 교양
    triggers.select_issue(conn, now, s)
    conn.execute(
        "INSERT INTO generation_requests (kind, topic, mode) VALUES ('culture', %s, 'immediate')",
        (psycopg.types.json.Jsonb(triggers.culture_topics(kst_today(now), 1)[0]),),
    )
    conn.commit()
    batch.submit_pending(conn, llm, s, now)
    process_received(conn, s, emb, llm, now)
    if s["review"]["enabled"]:
        auto_publish_pending(conn, s, emb, now)

    front = select_front(conn, kst_today(now), now, s)
    conn.commit()
    users = []
    for email, preset, weights in DEMO_USERS:
        uid = conn.execute(
            """INSERT INTO users (email, provider, plan) VALUES (%s, 'email', 'free')
               ON CONFLICT (email) DO UPDATE SET email = EXCLUDED.email RETURNING id""",
            (email,),
        ).fetchone()["id"]
        conn.execute(
            """INSERT INTO user_prefs (user_id, preset, section_weights) VALUES (%s, %s, %s)
               ON CONFLICT (user_id) DO UPDATE SET preset = EXCLUDED.preset, section_weights = EXCLUDED.section_weights""",
            (uid, preset, psycopg.types.json.Jsonb(weights)),
        )
        users.append({"email": email, "edition_id": assemble_and_save(conn, str(uid), now, s)})
    conn.commit()
    stats["posts"] = conn.execute("SELECT kind::text AS kind, count(*) AS n FROM posts GROUP BY 1 ORDER BY 1").fetchall()
    stats["front"] = front["seqs"]
    stats["users"] = users
    return stats
