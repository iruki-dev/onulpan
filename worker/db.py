"""Postgres 연결과 마이그레이션 러너.

메시지 큐를 두지 않는다. 큐는 jobs 테이블과 SELECT … FOR UPDATE SKIP LOCKED로 대신한다.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import numpy as np
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .settings import ROOT, settings

MIGRATIONS_DIR = ROOT / "db" / "migrations"


def connect(url: str | None = None) -> psycopg.Connection:
    return psycopg.connect(url or settings().database_url, row_factory=dict_row, autocommit=False)


@contextmanager
def transaction(conn: psycopg.Connection) -> Iterator[psycopg.Connection]:
    with conn.transaction():
        yield conn


def vec(v: np.ndarray | list[float] | None) -> str | None:
    """pgvector 리터럴. 어댑터 의존성을 두지 않으려고 문자열로 넘긴다."""
    if v is None:
        return None
    arr = np.asarray(v, dtype=np.float32)
    return "[" + ",".join(f"{x:.6f}" for x in arr.tolist()) + "]"


def parse_vec(s: Any) -> np.ndarray | None:
    if s is None:
        return None
    if isinstance(s, (list, tuple, np.ndarray)):
        return np.asarray(s, dtype=np.float32)
    return np.asarray(json.loads(s), dtype=np.float32)


def jsonb(v: Any) -> Jsonb:
    return Jsonb(v)


def log_decision(conn: psycopg.Connection, kind: str, ref: str, payload: dict) -> None:
    conn.execute(
        "INSERT INTO decision_log (kind, ref, payload) VALUES (%s, %s, %s)",
        (kind, ref, Jsonb(payload)),
    )


def migrate(conn: psycopg.Connection, directory: Path = MIGRATIONS_DIR) -> list[str]:
    """번호 순 SQL 파일을 한 번씩 적용한다."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations (name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
    )
    conn.commit()
    done = {r["name"] for r in conn.execute("SELECT name FROM schema_migrations").fetchall()}
    applied = []
    for path in sorted(directory.glob("*.sql")):
        if path.name in done:
            continue
        with conn.transaction():
            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (path.name,))
        applied.append(path.name)
    return applied
