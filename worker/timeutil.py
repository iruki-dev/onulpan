"""시각 도우미. 모든 일정은 KST 기준이다."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def now() -> datetime:
    return datetime.now(timezone.utc)


def kst(dt: datetime) -> datetime:
    return dt.astimezone(KST)


def kst_today(at: datetime | None = None) -> date:
    return kst(at or now()).date()


def kst_at(d: date, hhmm: str) -> datetime:
    h, m = (int(x) for x in hhmm.split(":"))
    return datetime.combine(d, time(h, m), tzinfo=KST)


def kst_day_bounds(d: date) -> tuple[datetime, datetime]:
    start = datetime.combine(d, time(0, 0), tzinfo=KST)
    return start, start + timedelta(days=1)


def hours_between(a: datetime, b: datetime) -> float:
    return (b - a).total_seconds() / 3600.0
