"""워커 명령 진입점. systemd 타이머가 이 명령들을 부른다 (infra/systemd).

    python -m worker.jobs.cli migrate
    python -m worker.jobs.cli collect | select | collect-batches | issue | auto-publish | front | assemble | send
    python -m worker.jobs.cli maintenance | culture-week | report-weekly | report-12w
    python -m worker.jobs.cli run-jobs          # 작업 큐 상주 프로세스
    python -m worker.jobs.cli scheduler         # systemd 없이 돌릴 때: 내부 시계로 위 작업을 KST 일정대로
    python -m worker.jobs.cli sync-outlets
    python -m worker.jobs.cli sync-image-sources # rules/image_sources.yaml → image_sources
    python -m worker.jobs.cli images            # 최근 글의 대표 이미지 찾기
    python -m worker.jobs.cli compare-models claude-sonnet-5 claude-sonnet-5-5 [--n 10] [--yes]  # 생성 모델 비교
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
from ..generate.models import load_retired
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
    "images": tasks.find_images,
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
        load_retired(conn)                  # 이전 실행에서 404로 확인한 모델은 처음부터 대체 모델로
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
    if m in (5, 20, 35, 50) or (h, m) == (6, 22):
        out.append("images")
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
    ap.add_argument("--n", type=int, default=10, help="compare-models: 비교할 최근 생성 요청 수")
    ap.add_argument("--kinds", default="fact,synthesis,issue", help="compare-models: 글 종류")
    ap.add_argument("--yes", action="store_true", help="compare-models: 실제로 호출한다 (없으면 예상 비용만)")
    args = ap.parse_args(argv)
    cmd = args.command
    s = settings()
    if cmd == "migrate":
        from ..images.policy import sync_sources

        with connect() as conn:
            print("applied:", migrate(conn))
            print("image sources:", sync_sources(conn))
            conn.commit()
        return 0
    if cmd == "sync-image-sources":
        from ..images.policy import sync_sources

        with connect() as conn:
            print("image sources:", sync_sources(conn))
            conn.commit()
        return 0
    if cmd == "sync-outlets":
        from ..collect.feeds import sync_outlets

        with connect() as conn:
            print("outlets:", sync_outlets(conn))
            conn.commit()
        return 0
    if cmd == "run-jobs":
        with connect() as conn:
            load_retired(conn)
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
    if cmd == "compare-models":
        from ..ops import compare
        from ..process.embed import get_embedder

        if len(args.rest) < 1:
            ap.error("compare-models 모델[@생각/노력] …  예: claude-sonnet-5 claude-sonnet-5-5")
        variants = [compare.parse_variant(x, s) for x in args.rest]
        est = compare.estimate_usd(variants, args.n)
        with connect() as conn:
            ok, msg = compare.budget_ok(conn, s, est)
            print(f"{len(variants)}개 설정 × 최근 {args.n}편 · {msg} (즉시 호출 정가 기준)")
            if not ok:
                return 1
            if not args.yes:
                print("실제로 비교하려면 --yes를 붙이세요.")
                return 0
            llm = tasks.get_llm()
            if llm is None:
                print("ANTHROPIC_API_KEY가 없습니다.")
                return 1
            out = compare.run(conn, s, llm, get_embedder(), args.rest, args.n, args.kinds.split(","), utcnow())
            print(json.dumps(out, ensure_ascii=False, default=str, indent=2))
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
