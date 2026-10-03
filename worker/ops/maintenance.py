"""03:00 정비: 원문 본문 30일 경과분 비우기, events 13개월 경과분 월별 집계 후 삭제, 사용량 집계."""
from __future__ import annotations

from datetime import datetime, timedelta

import psycopg

from ..db import log_decision


def purge_bodies(conn: psycopg.Connection, now: datetime, days: int = 30) -> int:
    """타인의 저작물을 장기 축적하지 않는다. 제목·URL·매체·시각은 영구 보관."""
    cur = conn.execute(
        """UPDATE raw_articles SET body = NULL, lead = NULL, body_purged_at = %s
           WHERE body IS NOT NULL AND fetched_at < %s""",
        (now, now - timedelta(days=days)),
    )
    return cur.rowcount


def rollup_events(conn: psycopg.Connection, now: datetime, months: int = 13) -> int:
    cutoff = (now.replace(day=1) - timedelta(days=31 * months)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    conn.execute(
        """INSERT INTO events_monthly (month, name, n_events, n_users)
           SELECT date_trunc('month', at)::date, name, count(*), count(DISTINCT COALESCE(user_id::text, anon_id))
           FROM events WHERE at < %s GROUP BY 1, 2
           ON CONFLICT (month, name) DO UPDATE SET n_events = events_monthly.n_events + EXCLUDED.n_events,
                                                  n_users = GREATEST(events_monthly.n_users, EXCLUDED.n_users)""",
        (cutoff,),
    )
    return conn.execute("DELETE FROM events WHERE at < %s", (cutoff,)).rowcount


def prune_work_tables(conn: psycopg.Connection, now: datetime) -> dict:
    return {
        "login_tokens": conn.execute("DELETE FROM login_tokens WHERE expires_at < %s", (now - timedelta(days=1),)).rowcount,
        "jobs": conn.execute("DELETE FROM jobs WHERE status = 'done' AND run_after < %s", (now - timedelta(days=30),)).rowcount,
    }


def usage_snapshot(conn: psycopg.Connection, now: datetime) -> dict:
    row = conn.execute(
        """SELECT
             (SELECT count(*) FROM raw_articles WHERE fetched_at > %(d)s) AS raw_24h,
             (SELECT count(*) FROM posts WHERE created_at > %(d)s) AS posts_24h,
             (SELECT COALESCE(sum(cost_usd),0) FROM llm_calls WHERE at > %(d)s) AS llm_usd_24h,
             (SELECT count(*) FROM email_sends WHERE sent_at > %(d)s) AS emails_24h,
             pg_database_size(current_database()) AS db_bytes""",
        {"d": now - timedelta(hours=24)},
    ).fetchone()
    snap = {k: (float(v) if not isinstance(v, int) else v) for k, v in row.items()}
    log_decision(conn, "usage", f"day:{now.date()}", snap)
    return snap


def run(conn: psycopg.Connection, now: datetime) -> dict:
    out = {"purged": purge_bodies(conn, now), "events_rolled": rollup_events(conn, now)}
    out.update(prune_work_tables(conn, now))
    out["usage"] = usage_snapshot(conn, now)
    conn.commit()
    return out
