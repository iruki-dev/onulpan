"""V9 충돌 명시: 원문 간 숫자가 다른데(V3 과정에서 탐지) conflicts가 비어 있으면 실패.

같은 항목(숫자 앞 낱말)·같은 단위인데 서로 다른 매체가 다른 값을 적었고, 본문이 그 항목을 숫자로 다룰 때만 본다.
"""
from __future__ import annotations

from collections import defaultdict

from ..base import Context, RuleResult, fail, ok, skip
from ..numbers import extract_numbers, is_date_like

ID = "V9"
COUNT_UNITS = {"명", "원", "달러", "%", "건", "가구", "채", "곳", "대", "척", "톤", "세대", "마리", "개국"}


def detect_conflicts(ctx: Context) -> dict[tuple[str, str], dict[tuple, set[float]]]:
    """같은 항목에 대해 두 매체가 겹치는 값 없이 서로 다른 값만 적었을 때를 충돌로 본다.
    (한 매체가 분기 실적과 연간 전망을 함께 적은 경우처럼 값이 겹치면 충돌이 아니다.)"""
    by_key: dict[tuple[str, str], dict[tuple, set[float]]] = defaultdict(lambda: defaultdict(set))
    for sid, d in ctx.docs.items():
        outlet = tuple(d.get("outlet_ids") or [sid])
        for n in extract_numbers(d["text"], with_context=True):
            if n.unit in COUNT_UNITS and len(n.context) >= 2 and not is_date_like(n):
                by_key[(n.context, n.unit)][outlet].add(n.value)
    out = {}
    for key, per_outlet in by_key.items():
        sets = list(per_outlet.values())
        if any(not (a & b) for i, a in enumerate(sets) for b in sets[i + 1:]):
            out[key] = per_outlet
    return out


def check(ctx: Context) -> RuleResult:
    if ctx.draft is None:
        return skip(ID, "parse_failed")
    if ctx.kind == "culture":
        return skip(ID, "교양: 원문 없음")
    conflicts = detect_conflicts(ctx)
    if not conflicts:
        return ok(ID)
    body_nums = extract_numbers(ctx.all_text, with_context=True)
    relevant = []
    for (context, unit), per_outlet in conflicts.items():
        if any(n.context == context and n.unit == unit for n in body_nums):
            values = sorted({v for vs in per_outlet.values() for v in vs})
            relevant.append(f"{context}({unit}): " + " / ".join(f"{v:g}" for v in values))
    if relevant and not (ctx.draft.get("conflicts") or []):
        return fail(ID, [f"원문끼리 다른 숫자를 conflicts에 밝히지 않음 — {r}" for r in relevant], detected=relevant)
    return ok(ID, detected=relevant)
