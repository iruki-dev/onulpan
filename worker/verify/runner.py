"""6단계 검증 러너. 규칙 검증(V1~V10)이 먼저이고, 출시 모드에서 LLM 의미 대조(V11)가 그 뒤에 붙는다.

검증을 통과하지 못한 글은 저장소에 들어오지 않는다. 지울 수 없는 저장소에서 품질 관리는 입구에서만 가능하다.
"""
from __future__ import annotations

import json
import logging
from typing import Callable

import psycopg

from ..generate.gateway import LLMClient
from ..generate.models import light_call
from ..generate.prompts import load_prompt, parse_json_output
from ..settings import Settings
from .base import Context, RuleResult
from .rules import ALL

log = logging.getLogger(__name__)


def run_rules(ctx: Context) -> dict:
    results: list[RuleResult] = []
    for rule in ALL:
        if rule.ID == "V11" and any(not r.ok for r in results):
            # 규칙에서 이미 걸린 초안에는 LLM 비용을 쓰지 않는다
            results.append(RuleResult("V11", True, "none", details={"reason": "앞 규칙 실패"}, skipped=True))
            continue
        try:
            results.append(rule.check(ctx))
        except Exception as e:  # 규칙 자체의 버그가 게시로 이어지지 않게 실패로 처리
            log.exception("rule %s crashed", rule.ID)
            results.append(RuleResult(rule.ID, False, "regen", [f"검증기 오류: {e}"]))
    failed = [r for r in results if not r.ok]
    if any(r.action == "discard" for r in failed):
        action = "discard"
    elif failed:
        action = "regen"
    else:
        action = "pass"
    return {
        "passed": not failed,
        "action": action,
        "mode": ctx.s.mode,
        "embedder": ctx.embedder_name,
        "rules": [r.to_json() for r in results],
    }


def failures_for_retry(report: dict, limit: int = 12) -> list[dict]:
    out = []
    for r in report["rules"]:
        if not r["ok"]:
            for m in r["messages"] or ["실패"]:
                out.append({"rule": r["id"], "message": m})
    return out[:limit]


def make_semantic_judge(conn: psycopg.Connection, llm: LLMClient, s: Settings) -> Callable:
    def judge(facts: list[str], sources: list[str]) -> list[dict] | None:
        user = "<facts>\n" + "\n".join(f"{i}. {f}" for i, f in enumerate(facts)) + "\n</facts>\n<sources>\n" + \
               "\n\n".join(sources) + "\n</sources>"
        res = light_call(conn, llm, s, "verify", load_prompt("semantic.v1"), user, 1024)
        if res is None or not res.ok:
            return None
        try:
            return list(parse_json_output(res.text).get("unsupported") or [])
        except (ValueError, json.JSONDecodeError):
            return None

    return judge


def make_gray_judge(conn: psycopg.Connection, llm: LLMClient, s: Settings) -> Callable:
    """3단계 회색 구간 판정 (출시 모드)."""
    def judge(article: str, titles: list[str]) -> bool | None:
        user = f"<news_a>\n{article[:800]}\n</news_a>\n<news_b>\n" + "\n".join(titles) + "\n</news_b>"
        res = light_call(conn, llm, s, "cluster_gray", load_prompt("gray.v1"), user, 256)
        if res is None or not res.ok:
            return None
        try:
            return bool(parse_json_output(res.text).get("same_event"))
        except (ValueError, json.JSONDecodeError):
            return None

    return judge
