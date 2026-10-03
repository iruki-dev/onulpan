import os
from datetime import datetime, timezone

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://onulpan:onulpan@localhost:5432/onulpan_test")
os.environ.setdefault("ONULPAN_EMBEDDER", "hashing")
os.environ.setdefault("ONULPAN_SECRET", "test-secret")
os.environ.pop("ANTHROPIC_API_KEY", None)

from worker.db import connect, migrate  # noqa: E402
from worker.settings import load_settings  # noqa: E402

# 고정 시각: 2026-10-06(화) 07:00 KST
NOW = datetime(2026, 10, 5, 22, 0, tzinfo=timezone.utc)


@pytest.fixture
def now():
    return NOW


@pytest.fixture
def s():
    return load_settings("beta")


@pytest.fixture
def s_launch():
    return load_settings("launch", {"review": {"enabled": False}})


@pytest.fixture
def conn():
    """테스트마다 빈 스키마. 추가 전용 테이블은 TRUNCATE가 막혀 있으므로 스키마째 다시 만든다."""
    c = connect(os.environ["DATABASE_URL"])
    c.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    c.commit()
    migrate(c)
    yield c
    c.rollback()
    c.close()
