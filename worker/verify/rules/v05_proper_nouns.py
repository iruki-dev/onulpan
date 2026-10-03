"""V5 고유명사: kiwipiepy로 본문의 고유명사(NNP)를 뽑아 원문 또는 slug 표시 이름에 있는지 확인.
조사 제거 후 부분 일치 허용."""
from __future__ import annotations

from ...nlp import proper_nouns
from ..base import Context, RuleResult, fail, ok, skip, squash

ID = "V5"


def check(ctx: Context) -> RuleResult:
    if ctx.draft is None:
        return skip(ID, "parse_failed")
    if ctx.kind == "culture":
        return skip(ID, "교양: 원문 없음")
    hay = squash(ctx.source_text)
    allowed = {squash(n) for n in ctx.names if n}
    missing = []
    for nnp in proper_nouns(ctx.all_text):
        k = squash(nnp)
        if k in hay or k in allowed or any(k in a or a in k for a in allowed if len(a) >= 2):
            continue
        # 부분 일치: 앞 2/3 이상이 원문에 있으면 (예: ‘한국은행’ ↔ ‘한은’은 허용하지 않음, ‘이창용’ ↔ ‘이창용씨’는 허용)
        if len(k) >= 3 and k[: max(2, len(k) - 1)] in hay:
            continue
        missing.append(nnp)
    if missing:
        return fail(ID, [f"원문에 없는 고유명사: {m}" for m in missing], nnps=missing)
    return ok(ID)
