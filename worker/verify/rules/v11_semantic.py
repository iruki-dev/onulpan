"""V11 의미 대조 (출시 모드): Haiku 4.5에 facts[]와 인용 원문을 주고 원문이 뒷받침하지 않는 사실을 JSON으로 받는다."""
from __future__ import annotations

from ..base import Context, RuleResult, fail, ok, skip

ID = "V11"


def check(ctx: Context) -> RuleResult:
    if not ctx.s["verify"].get("semantic_llm"):
        return skip(ID, "베타 모드: 규칙 검증만")
    if ctx.draft is None:
        return skip(ID, "parse_failed")
    if ctx.kind == "culture":
        return skip(ID, "교양: 원문 없음")
    if ctx.semantic_judge is None:
        return skip(ID, "판정기 없음")
    facts = [f.get("text", "") for f in ctx.draft.get("facts") or [] if isinstance(f, dict)]
    cited = {sid for f in ctx.draft.get("facts") or [] if isinstance(f, dict) for sid in f.get("source_ids") or []}
    sources = [f"[{sid}] {ctx.docs[sid]['text']}" for sid in sorted(cited) if sid in ctx.docs]
    unsupported = ctx.semantic_judge(facts, sources)
    if unsupported is None:
        return skip(ID, "판정 실패")
    if unsupported:
        msgs = []
        for u in unsupported:
            i = u.get("index", -1)
            fact = facts[i] if isinstance(i, int) and 0 <= i < len(facts) else "?"
            msgs.append(f"원문이 뒷받침하지 않는 사실: {fact[:40]} — {u.get('reason', '')}")
        return fail(ID, msgs, unsupported=unsupported)
    return ok(ID)
