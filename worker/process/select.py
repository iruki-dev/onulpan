"""4단계 생성 대상 선정 (매시 정각).

조건: 매체 2곳 이상, 마지막 기사 24시간 이내, 60분간 새 기사가 없거나 기사 5건 이상(안정화).
중요도 순으로 하루 상한(베타 30, 출시 150)까지. 1면 후보(중요도 상위 5)와 속보성 묶음만 즉시 호출한다.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import psycopg

from ..db import log_decision
from ..settings import Settings
from ..timeutil import kst_day_bounds, kst_today
from .importance import explain, importance


def daily_count(conn: psycopg.Connection, kind: str, now: datetime) -> int:
    start, end = kst_day_bounds(kst_today(now))
    return conn.execute(
        "SELECT count(*) AS n FROM generation_requests WHERE kind = %s AND attempt = 1 AND created_at >= %s AND created_at < %s",
        (kind, start, end),
    ).fetchone()["n"]


def eligible_clusters(conn: psycopg.Connection, now: datetime, s: Settings) -> list[dict]:
    c = s["select"]
    rows = conn.execute(
        """SELECT c.*,
                  (SELECT count(DISTINCT r.outlet_id) FROM raw_articles r
                    WHERE r.cluster_id = c.id AND r.duplicate_of IS NULL AND r.body IS NOT NULL) AS n_source_outlets
           FROM clusters c
           WHERE c.state = 'open'
             AND c.last_seen >= %(recent)s
             AND (c.last_seen <= %(quiet)s OR c.n_articles >= %(stable)s)
             AND NOT EXISTS (SELECT 1 FROM generation_requests g
                             WHERE g.cluster_id = c.id AND g.kind IN ('fact','issue')
                               AND g.status NOT IN ('expired'))""",
        {"recent": now - timedelta(hours=c["recent_hours"]),
         "quiet": now - timedelta(minutes=c["quiet_minutes"]),
         "stable": c["stable_articles"]},
    ).fetchall()
    imp = s["importance"]
    out = []
    for r in rows:
        if r["n_source_outlets"] < c["min_outlets"]:
            continue
        r["importance"] = importance(r["n_outlets"], r["n_groups"], r["last_seen"], now, imp["group_bonus"], imp["decay_hours"])
        out.append(r)
    out.sort(key=lambda r: (-r["importance"], r["id"]))
    return out


def select_targets(conn: psycopg.Connection, now: datetime, s: Settings) -> list[int]:
    c = s["select"]
    remaining = c["daily_cap"] - daily_count(conn, "fact", now)
    cands = eligible_clusters(conn, now, s)
    created = []
    imp = s["importance"]
    for rank, r in enumerate(cands):
        if remaining <= 0:
            break
        breaking = (r["first_seen"] >= now - timedelta(hours=c["breaking_hours"])
                    and r["n_outlets"] >= c["breaking_outlets"])
        mode = "immediate" if rank < c["immediate_top"] or breaking else "batch"
        rid = conn.execute(
            """INSERT INTO generation_requests (kind, cluster_id, priority, mode, created_at)
               VALUES ('fact', %s, %s, %s, %s) RETURNING id""",
            (r["id"], r["importance"], mode, now),
        ).fetchone()["id"]
        log_decision(conn, "target", f"cluster:{r['id']}", {
            "request_id": rid, "rank": rank, "mode": mode, "breaking": breaking,
            **explain(r["n_outlets"], r["n_groups"], r["last_seen"], now, imp["group_bonus"], imp["decay_hours"]),
        })
        created.append(rid)
        remaining -= 1
    return created


def expire_stale(conn: psycopg.Connection, now: datetime, s: Settings) -> int:
    """LLM이 멈춘 동안 쌓인 대기열 중 36시간이 지난 것은 버린다."""
    cur = conn.execute(
        """UPDATE generation_requests SET status = 'expired', finished_at = %s
           WHERE status = 'pending' AND created_at < %s""",
        (now, now - timedelta(hours=s["select"]["expire_hours"])),
    )
    return cur.rowcount
