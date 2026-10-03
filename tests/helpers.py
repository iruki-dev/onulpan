"""테스트 도우미: 가상 하루치를 DB에 넣고 파이프라인을 돌린다."""
from __future__ import annotations

from datetime import timedelta

from worker.dev.demo import ensure_outlets
from worker.dev.fake import FakeLLM, KeywordEmbedder, article_times, build_events
from worker.generate import batch
from worker.pipeline import auto_publish_pending, process_received
from worker.process.embed import set_embedder
from worker.process.ingest import ingest_article
from worker.process.select import select_targets


def setup_day(conn, s, now, events=None):
    events = events or build_events(now - timedelta(hours=4))
    emb = KeywordEmbedder([e["key"] for e in events])
    set_embedder(emb)
    outlets = ensure_outlets(conn)
    for ev in events:
        for i, a in enumerate(ev["articles"]):
            ingest_article(conn, s, emb, outlet_id=outlets[a["outlet"]],
                           url=f"https://{outlets[a['outlet']]}.demo.invalid/{ev['key']}/{i}", title=a["title"],
                           body=a["body"], published_at=article_times(now, a["hours_ago"]))
    conn.commit()
    return events, emb, outlets


def run_generation(conn, s, now, llm, emb, rounds=2):
    select_targets(conn, now, s)
    conn.commit()
    for _ in range(rounds):
        batch.submit_pending(conn, llm, s, now)
        batch.collect_batches(conn, llm, s, now)
        process_received(conn, s, emb, llm, now)
    if s["review"]["enabled"]:
        auto_publish_pending(conn, s, emb, now)


def full_day(conn, s, now, mutate=None):
    events, emb, outlets = setup_day(conn, s, now)
    llm = FakeLLM(events, mutate=mutate)
    run_generation(conn, s, now, llm, emb)
    return events, emb, llm
