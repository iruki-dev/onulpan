"""수집한 기사 한 건을 2~3단계(정규화·중복 제거·임베딩·묶기)에 통과시켜 raw_articles에 넣는다."""
from __future__ import annotations

from datetime import datetime, timedelta

import psycopg

from ..collect.urls import normalize_url
from ..db import log_decision, vec
from ..nlp import normalize_ws, proper_nouns
from ..settings import Settings
from . import cluster
from .embed import Embedder
from .normalize import clean_body, lead_of
from .simhash import simhash


def ingest_article(conn: psycopg.Connection, s: Settings, embedder: Embedder, *, outlet_id: int, url: str,
                   title: str, body: str, published_at: datetime,
                   gray_judge: cluster.GrayJudge | None = None) -> int | None:
    url = normalize_url(url)
    title = normalize_ws(title)
    if conn.execute("SELECT 1 FROM raw_articles WHERE url = %s", (url,)).fetchone():
        return None
    body = clean_body(body)
    sh = simhash(title + "\n" + body, s["dedup"]["shingle"])
    dup = conn.execute(
        """SELECT id, cluster_id FROM raw_articles
           WHERE duplicate_of IS NULL AND published_at >= %s
             AND bit_count((simhash # %s::bigint)::bit(64)) <= %s
           ORDER BY id LIMIT 1""",
        (published_at - timedelta(hours=s["dedup"]["lookback_hours"]), sh, s["dedup"]["hamming_max"]),
    ).fetchone()
    lead = lead_of(title, body, s["cluster"]["embed_input_chars"])
    nnps = proper_nouns(lead)

    if dup:
        aid = conn.execute(
            """INSERT INTO raw_articles (outlet_id, url, title, body, lead, published_at, simhash, duplicate_of, cluster_id, nnps)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (outlet_id, url, title, body, lead, published_at, sh, dup["id"], dup["cluster_id"], nnps),
        ).fetchone()["id"]
        log_decision(conn, "assign", f"raw:{aid}", {"article_id": aid, "rule": "duplicate",
                                                     "duplicate_of": dup["id"], "cluster_id": dup["cluster_id"]})
        if dup["cluster_id"]:
            cluster.refresh_cluster_stats(conn, dup["cluster_id"])
        return aid

    emb = embedder.embed([lead])[0]
    aid = conn.execute(
        """INSERT INTO raw_articles (outlet_id, url, title, body, lead, published_at, simhash, embedding, nnps)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s::vector,%s) RETURNING id""",
        (outlet_id, url, title, body, lead, published_at, sh, vec(emb), nnps),
    ).fetchone()["id"]
    cluster.assign(conn, aid, emb, nnps, lead, published_at, s, gray_judge)
    return aid
