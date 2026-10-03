"""워커 명령 진입점. systemd 타이머가 이 명령들을 부른다 (infra/systemd).

    python -m worker.jobs.cli migrate
    python -m worker.jobs.cli collect | select | collect-batches | issue | auto-publish | front | assemble | send
    python -m worker.jobs.cli maintenance | culture-week | report-weekly | report-12w
    python -m worker.jobs.cli run-jobs          # 작업 큐 상주 프로세스
    python -m worker.jobs.cli scheduler         # systemd 없이 돌릴 때: 내부 시계로 위 작업을 KST 일정대로
    python -m worker.jobs.cli sync-outlets
    python -m worker.jobs.cli seed-demo         # 개발용: 가상 기사·글로 웹을 띄워 볼 수 있게
    python -m worker.jobs.cli alert backup_failed "메시지"
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time

from ..db import connect, migrate
from ..settings import settings
from ..timeutil import kst, now as utcnow
from . import queue, tasks

TASKS = {
    "collect": tasks.collect,
    "select": tasks.hourly_select,
    "collect-batches": tasks.hourly_collect,
    "issue": tasks.issue_select,
    "auto-publish": tasks.auto_publish,
    "front": tasks.front,
    "assemble": tasks.assemble_morning,
    "send": tasks.send_emails,
    "maintenance": tasks.maintenance_daily,
    "culture-week": tasks.culture_week,
}


def _with_lock(conn, name: str, fn):
    """같은 작업이 겹쳐 돌지 않게 한다 (예: 수집이 15분을 넘긴 경우)."""
    got = conn.execute("SELECT pg_try_advisory_lock(hashtext(%s)) AS ok", (f"task:{name}",)).fetchone()["ok"]
    conn.commit()
    if not got:
        return {"skipped": "already running"}
    try:
        return fn()
    finally:
        conn.execute("SELECT pg_advisory_unlock(hashtext(%s))", (f"task:{name}",))
        conn.commit()


def run_task(name: str) -> dict:
    s = settings()
    with connect() as conn:
        return _with_lock(conn, name, lambda: TASKS[name](conn, s, utcnow()))


# 내부 스케줄러: (분 조건, 시 조건, 요일 조건, 작업)
def _due(now_kst) -> list[str]:
    m, h, wd = now_kst.minute, now_kst.hour, now_kst.weekday()  # 월=0 … 일=6
    out = []
    if m % 15 == 0:
        out.append("collect")
    if m == 0:
        out.append("select")
    if m == 30:
        out.append("collect-batches")
    if (h, m) == (3, 0):
        out.append("maintenance")
    if (h, m) == (4, 30):
        out.append("issue")
    if (h, m) == (6, 20):
        out.append("auto-publish")
    if (h, m) == (6, 25):
        out.append("front")
    if (h, m) == (6, 30):
        out.append("assemble")
    if 7 <= h <= 10 and m % 10 == 0:
        out.append("send")
    if (wd, h, m) == (6, 22, 0):
        out.append("culture-week")
    return out


def scheduler() -> None:
    log = logging.getLogger("scheduler")
    last = None
    while True:
        n = kst(utcnow()).replace(second=0, microsecond=0)
        if n != last:
            last = n
            for name in _due(n):
                try:
                    log.info("%s %s", name, json.dumps(run_task(name), ensure_ascii=False, default=str))
                except Exception:  # noqa: BLE001 — 한 작업의 실패가 다른 작업을 막지 않는다
                    log.exception("task %s failed", name)
        time.sleep(5)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    ap = argparse.ArgumentParser(prog="worker")
    ap.add_argument("command")
    ap.add_argument("rest", nargs="*")
    args = ap.parse_args(argv)
    cmd = args.command
    s = settings()
    if cmd == "migrate":
        with connect() as conn:
            print("applied:", migrate(conn))
        return 0
    if cmd == "sync-outlets":
        from ..collect.feeds import sync_outlets

        with connect() as conn:
            print("outlets:", sync_outlets(conn))
            conn.commit()
        return 0
    if cmd == "run-jobs":
        with connect() as conn:
            queue.run_forever(conn, s, tasks.handle_job)
        return 0
    if cmd == "scheduler":
        scheduler()
        return 0
    if cmd == "report-weekly":
        from ..ops import reports

        with connect() as conn:
            print(reports.weekly_quality(conn, utcnow()))
        return 0
    if cmd == "report-12w":
        from ..ops import reports

        with connect() as conn:
            print(reports.twelve_week(conn, utcnow()))
        return 0
    if cmd == "alert":
        # infra/backup.sh 등 셸 스크립트에서: python -m worker.jobs.cli alert backup_failed "메시지"
        from ..ops import alerts

        kind = args.rest[0]
        text = " ".join(args.rest[1:]) or kind
        with connect() as conn:
            alerts.alert(conn, kind, kst(utcnow()).strftime("%Y-%m-%dT%H"), text)
        return 0
    if cmd == "seed-demo":
        from ..dev.demo import seed

        with connect() as conn:
            print(json.dumps(seed(conn, s), ensure_ascii=False, default=str, indent=2))
        return 0
    if cmd in TASKS:
        print(json.dumps(run_task(cmd), ensure_ascii=False, default=str, indent=2))
        return 0
    ap.error(f"unknown command {cmd}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
