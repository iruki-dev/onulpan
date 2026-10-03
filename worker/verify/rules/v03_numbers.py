"""V3 숫자: 본문의 숫자 표현을 단위까지 정규화한 뒤, 입력 원문 중 한 곳에 같은 값이 있는지 확인."""
from __future__ import annotations

from ..base import Context, RuleResult, fail, ok, skip, without_quotes
from ..numbers import extract_numbers, is_date_like

ID = "V3"


def source_values(ctx: Context) -> tuple[set[tuple[float, str]], set[float]]:
    pairs: set[tuple[float, str]] = set()
    values: set[float] = set()
    for d in ctx.docs.values():
        for n in extract_numbers(d["text"]):
            pairs.add((n.value, n.unit))
            values.add(n.value)
    return pairs, values


def check(ctx: Context) -> RuleResult:
    if ctx.draft is None:
        return skip(ID, "parse_failed")
    if ctx.kind == "culture":
        return skip(ID, "교양: 원문 없음")
    pairs, values = source_values(ctx)
    missing = []
    for n in extract_numbers(ctx.all_text):
        if is_date_like(n):
            continue  # V4가 본다
        if (n.value, n.unit) in pairs:
            continue
        if n.unit == "" and n.value in values:
            continue
        if n.unit != "" and (n.value, "") in pairs:
            continue  # 원문에서 단위가 떨어져 있는 경우 (예: "12,000 명")
        missing.append(n.raw)
    if missing:
        return fail(ID, [f"원문에 없는 숫자: {m}" for m in dict.fromkeys(missing)], numbers=list(dict.fromkeys(missing)))
    return ok(ID)
