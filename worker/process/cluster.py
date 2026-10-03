"""3단계 묶기.

48시간 이내 열린 묶음 중심과 코사인 0.82 이상이면 합류, 0.70~0.82는 회색 구간, 0.70 미만이면 새 묶음.
회색 구간(베타, LLM 없이): 묶음 대표 기사들과 고유명사를 2개 이상 공유하고, 묶음의 마지막 기사와 12시간 이내일 때만 합류.
불확실하면 새 묶음을 연다. 잘못 나뉘면 중복 글 1편이지만, 잘못 합쳐지면 사실이 섞인 글이 나오기 때문이다.
모든 판단은 decision_log(kind='assign')에 남긴다.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable

import numpy as np
import psycopg

from ..db import log_decision, parse_vec, vec
from ..settings import Settings

GrayJudge = Callable[[str, list[str]], bool | None]  # (기사 제목+리드, 묶음 대표 제목들) → 같은 사건?


def _rep_nnps(conn: psycopg.Connection, cluster_id: int, n: int) -> tuple[set[str], list[str]]:
    rows = conn.execute(
        """SELECT title, nnps FROM raw_articles
           WHERE cluster_id = %s AND duplicate_of IS NULL
           ORDER BY published_at DESC LIMIT %s""",
        (cluster_id, n),
    ).fetchall()
    nnps: set[str] = set()
    for r in rows:
        nnps.update(r["nnps"] or [])
    return nnps, [r["title"] for r in rows]


def refresh_cluster_stats(conn: psycopg.Connection, cluster_id: int) -> None:
    conn.execute(
        """UPDATE clusters c SET
             n_articles = s.n_articles, n_outlets = s.n_outlets, n_groups = s.n_groups,
             first_seen = s.first_seen, last_seen = s.last_seen
           FROM (SELECT count(*) AS n_articles,
                        count(DISTINCT r.outlet_id) AS n_outlets,
                        count(DISTINCT o.grp) AS n_groups,
                        min(r.published_at) AS first_seen,
                        max(r.published_at) AS last_seen
                 FROM raw_articles r JOIN outlets o ON o.id = r.outlet_id
                 WHERE r.cluster_id = %(id)s) s
           WHERE c.id = %(id)s""",
        {"id": cluster_id},
    )


def assign(conn: psycopg.Connection, article_id: int, embedding: np.ndarray, nnps: list[str],
           text_for_judge: str, published_at: datetime, s: Settings,
           gray_judge: GrayJudge | None = None) -> int:
    c = s["cluster"]
    since = published_at - timedelta(hours=c["window_hours"])
    best = conn.execute(
        """SELECT id, centroid::text AS centroid, last_seen, n_articles,
                  1 - (centroid <=> %(e)s::vector) AS sim
           FROM clusters
           WHERE state IN ('open','written') AND last_seen >= %(since)s
           ORDER BY centroid <=> %(e)s::vector LIMIT 1""",
        {"e": vec(embedding), "since": since},
    ).fetchone()

    decision: dict = {"article_id": article_id, "nnps": nnps[:20]}
    join_id: int | None = None
    if best is not None:
        sim = float(best["sim"])
        decision.update(candidate=best["id"], similarity=round(sim, 4))
        if sim >= c["join"]:
            join_id, decision["rule"] = best["id"], "join"
        elif sim >= c["gray_low"]:
            rep, titles = _rep_nnps(conn, best["id"], c["rep_articles"])
            shared = sorted(set(nnps) & rep)
            gap_h = abs((published_at - best["last_seen"]).total_seconds()) / 3600
            decision.update(gray=True, shared_nnps=shared, gap_hours=round(gap_h, 2))
            verdict = None
            if c.get("gray_llm") and gray_judge is not None:
                verdict = gray_judge(text_for_judge, titles)
                decision["llm_same_event"] = verdict
            if verdict is None:
                verdict = len(shared) >= c["gray_shared_nnp_min"] and gap_h <= c["gray_max_gap_hours"]
            if verdict:
                join_id, decision["rule"] = best["id"], "gray_join"
            else:
                decision["rule"] = "gray_new"
        else:
            decision["rule"] = "new"
    else:
        decision["rule"] = "new_empty"

    if join_id is None:
        join_id = conn.execute(
            """INSERT INTO clusters (centroid, first_seen, last_seen, n_articles, n_outlets, n_groups)
               VALUES (%s::vector, %s, %s, 0, 0, 0) RETURNING id""",
            (vec(embedding), published_at, published_at),
        ).fetchone()["id"]
    else:
        # 중심은 (중복이 아닌) 기사 임베딩의 평균
        n = conn.execute(
            "SELECT count(*) AS n FROM raw_articles WHERE cluster_id = %s AND embedding IS NOT NULL", (join_id,)
        ).fetchone()["n"]
        centroid = parse_vec(best["centroid"])
        new = (centroid * n + embedding) / (n + 1)
        norm = float(np.linalg.norm(new))
        conn.execute("UPDATE clusters SET centroid = %s::vector WHERE id = %s",
                     (vec(new / norm if norm else new), join_id))

    conn.execute("UPDATE raw_articles SET cluster_id = %s WHERE id = %s", (join_id, article_id))
    refresh_cluster_stats(conn, join_id)
    decision["cluster_id"] = join_id
    log_decision(conn, "assign", f"raw:{article_id}", decision)
    return join_id


def close_stale(conn: psycopg.Connection, now: datetime, s: Settings) -> int:
    cur = conn.execute(
        """UPDATE clusters SET state = 'closed'
           WHERE state IN ('open','written') AND last_seen < %s""",
        (now - timedelta(hours=s["cluster"]["close_after_hours"]),),
    )
    return cur.rowcount
