"""작업 큐: jobs 테이블과 SELECT … FOR UPDATE SKIP LOCKED. 메시지 큐를 따로 두지 않는다."""
from __future__ import annotations

import logging
import time
from datetime import timedelta

import psycopg

from ..db import jsonb
from ..settings import Settings
from ..timeutil import now as utcnow

log = logging.getLogger(__name__)
MAX_ATTEMPTS = 3


def enqueue(conn: psycopg.Connection, type_: str, payload: dict) -> int:
    return conn.execute("INSERT INTO jobs (type, payload) VALUES (%s, %s) RETURNING id", (type_, jsonb(payload))).fetchone()["id"]


def claim(conn: psycopg.Connection) -> dict | None:
    row = conn.execute(
        """UPDATE jobs SET status = 'running', attempts = attempts + 1
           WHERE id = (SELECT id FROM jobs WHERE status = 'queued' AND run_after <= now()
                       ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1)
           RETURNING *"""
    ).fetchone()
    conn.commit()
    return row


def run_once(conn: psycopg.Connection, s: Settings, handler) -> bool:
    job = claim(conn)
    if job is None:
        return False
    try:
        handler(conn, s, job, utcnow())
        conn.execute("UPDATE jobs SET status = 'done', last_error = NULL WHERE id = %s", (job["id"],))
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        log.exception("job %s failed", job["id"])
        if job["attempts"] >= MAX_ATTEMPTS:
            conn.execute("UPDATE jobs SET status = 'failed', last_error = %s WHERE id = %s", (str(e)[:1000], job["id"]))
        else:
            conn.execute("UPDATE jobs SET status = 'queued', last_error = %s, run_after = now() + %s WHERE id = %s",
                         (str(e)[:1000], timedelta(minutes=job["attempts"]), job["id"]))
    conn.commit()
    return True


def run_forever(conn: psycopg.Connection, s: Settings, handler, idle_sleep: float = 1.0) -> None:
    """웹에서 설정을 바꾸면 수 초 이내에 재조립된다."""
    while True:
        if not run_once(conn, s, handler):
            time.sleep(idle_sleep)
