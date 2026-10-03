"""V8 금지 표현: 주어 없는 표현과 평가 형용사 목록(rules/banned_phrases.txt)을 정규식으로 검사."""
from __future__ import annotations

import re
from functools import lru_cache

from ...settings import RULES_DIR
from ..base import Context, RuleResult, fail, ok, skip, without_quotes

ID = "V8"


@lru_cache(maxsize=1)
def patterns() -> list[tuple[str, re.Pattern]]:
    out = []
    for line in (RULES_DIR / "banned_phrases.txt").read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        if "\t" in line:
            cat, pat = line.split("\t", 1)
        else:
            cat, pat = "misc", line
        out.append((cat.strip(), re.compile(pat.strip())))
    return out


def check(ctx: Context) -> RuleResult:
    if ctx.draft is None:
        return skip(ID, "parse_failed")
    quotes = [q.get("text", "") for q in ctx.draft.get("quotes") or []]
    text = without_quotes(ctx.all_text, quotes)  # 발언자의 말은 인용으로 옮길 수 있다
    hits = []
    for cat, p in patterns():
        for m in p.finditer(text):
            hits.append((cat, m.group(0)))
    if hits:
        return fail(ID, [f"금지 표현({c}): ‘{h}’" for c, h in hits], hits=[h for _, h in hits])
    return ok(ID)
