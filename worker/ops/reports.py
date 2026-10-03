"""주간 품질 리포트(일요일 22:00)와 12주 결과 리포트. 모두 기존 테이블·뷰에 대한 SQL이다. reports/에 마크다운으로 남긴다."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import psycopg

from ..settings import ROOT
from ..timeutil import kst_today

REPORTS = ROOT / "reports"


def _table(rows: list[dict], cols: list[str]) -> str:
    if not rows:
        return "_(자료 없음)_\n"
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        out.append("| " + " | ".join("" if r.get(c) is None else str(r.get(c)) for c in cols) + " |")
    return "\n".join(out) + "\n"


def weekly_quality(conn: psycopg.Connection, now: datetime) -> Path:
    end = kst_today(now)
    start = end - timedelta(days=7)
    q = conn.execute("SELECT * FROM v_quality_daily WHERE day > %s AND day <= %s ORDER BY day", (start, end)).fetchall()
    rules = conn.execute(
        """SELECT rule_id, sum(checked) AS checked, sum(failed) AS failed,
                  round(100.0 * sum(failed) / NULLIF(sum(checked),0), 1) AS fail_pct
           FROM v_verify_rule_daily WHERE day > %s AND day <= %s GROUP BY rule_id
           ORDER BY substring(rule_id from 2)::int""",
        (start, end),
    ).fetchall()
    review = conn.execute("SELECT * FROM v_review_weekly ORDER BY week DESC LIMIT 6").fetchall()
    cost = conn.execute(
        "SELECT purpose, sum(calls) AS calls, round(sum(cost_usd)::numeric, 4) AS cost_usd FROM v_llm_cost_daily "
        "WHERE day > %s AND day <= %s GROUP BY purpose ORDER BY 3 DESC",
        (start, end),
    ).fetchall()
    sample = conn.execute(
        """SELECT id, ref, payload->>'rule' AS rule, payload->>'similarity' AS sim, payload->'shared_nnps' AS shared
           FROM decision_log WHERE kind = 'assign' AND at > %s AND payload->>'rule' IN ('join','gray_join','gray_new')
           ORDER BY md5(id::text) LIMIT 50""",
        (now - timedelta(days=7),),
    ).fetchall()
    front = conn.execute("SELECT * FROM v_front_section_monthly ORDER BY month DESC, n DESC LIMIT 12").fetchall()
    md = [f"# 주간 품질 리포트 {start + timedelta(days=1)} ~ {end}\n",
          "## 검증 통과율과 폐기율 (목표: 통과 80% 이상, 폐기 5% 미만)\n",
          _table(q, ["day", "generated", "passed_first", "pass_pct", "selected_clusters", "skipped_clusters", "discard_pct"]),
          "\n## 규칙별 실패율\n", _table(rules, ["rule_id", "checked", "failed", "fail_pct"]),
          "\n## 사람 반려율 (베타, 목표: 4주 연속 1% 미만 → 사람 검토 해제)\n",
          _table(review, ["week", "reviewed", "rejected", "auto_published", "reject_pct"]),
          "\n## LLM 비용\n", _table(cost, ["purpose", "calls", "cost_usd"]),
          "\n## 1면 섹션 분포 (한 섹션 월 50% 초과 금지)\n", _table(front, ["month", "section", "n", "pct"]),
          "\n## 묶기 표본 50건 (수동 판정용: 잘못 합친 것에 표시)\n",
          _table(sample, ["id", "ref", "rule", "sim", "shared"])]
    REPORTS.mkdir(exist_ok=True)
    path = REPORTS / f"weekly-{end}.md"
    path.write_text("\n".join(md), encoding="utf-8")
    return path


def twelve_week(conn: psycopg.Connection, now: datetime, start: date = date(2026, 10, 5)) -> Path:
    end = kst_today(now)
    habit = conn.execute(
        """WITH days AS (
             SELECT user_id, count(DISTINCT kst_date(at)) AS days FROM events
             WHERE name = 'edition_open' AND user_id IS NOT NULL AND at > %s GROUP BY user_id)
           SELECT count(*) FILTER (WHERE days >= 5) AS habitual, count(*) AS active,
                  round(100.0 * count(*) FILTER (WHERE days >= 5) / NULLIF(count(*),0), 1) AS habit_pct
           FROM days""",
        (now - timedelta(days=7),),
    ).fetchone()
    links = conn.execute(
        """SELECT count(*) FILTER (WHERE name = 'link_click') AS clicks,
                  count(DISTINCT (COALESCE(user_id::text, anon_id), kst_date(at))) FILTER (WHERE name = 'edition_open') AS opens
           FROM events WHERE at > %s""",
        (now - timedelta(days=28),),
    ).fetchone()
    link_rate = round(100.0 * links["clicks"] / links["opens"], 1) if links["opens"] else None
    channels = conn.execute(
        "SELECT channel, sum(signups) AS signups FROM v_signups_daily WHERE day >= %s GROUP BY channel ORDER BY 2 DESC",
        (start,),
    ).fetchall()
    pay = conn.execute(
        """SELECT (SELECT count(DISTINCT user_id) FROM payments WHERE status = 'paid') AS paid,
                  (SELECT count(*) FROM users WHERE deleted_at IS NULL) AS users""",
    ).fetchone()
    conv = round(100.0 * pay["paid"] / pay["users"], 2) if pay["users"] else None
    md = [f"# 12주 결과 리포트 ({start} ~ {end})\n",
          "## 습관률 (최근 7일 중 5일 이상 조간을 연 사람 / 연 적 있는 사람)\n", _table([habit], ["habitual", "active", "habit_pct"]),
          f"\n## 링크 탐색률 (최근 28일 링크 클릭 / 조간 열람): {link_rate}%\n",
          "\n## 채널별 가입\n", _table(channels, ["channel", "signups"]),
          f"\n## 선결제 전환율: {conv}% ({pay['paid']} / {pay['users']})\n"]
    REPORTS.mkdir(exist_ok=True)
    path = REPORTS / f"12weeks-{end}.md"
    path.write_text("\n".join(md), encoding="utf-8")
    return path
