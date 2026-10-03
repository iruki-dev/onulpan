"""V2 출처 수: facts[].source_ids의 매체가 서로 다른 곳 2개 이상. 부족하면 폐기 (재생성해도 해결 안 됨)."""
from __future__ import annotations

from ..base import Context, RuleResult, fail, ok, skip

ID = "V2"


def check(ctx: Context) -> RuleResult:
    if ctx.draft is None:
        return skip(ID, "parse_failed")
    if ctx.kind == "culture":
        return skip(ID, "교양: 편집 캘린더 글, 뉴스 출처 없음")
    cited: set[str] = set()
    unknown: set[str] = set()
    for f in ctx.draft.get("facts") or []:
        for sid in (f.get("source_ids") or []) if isinstance(f, dict) else []:
            (cited if sid in ctx.docs else unknown).add(sid)
    if ctx.kind == "issue":
        for p in (ctx.draft.get("sections") or {}).get("positions") or []:
            for sid in p.get("source_ids") or []:
                (cited if sid in ctx.docs else unknown).add(sid)
    if unknown:
        return fail(ID, [f"입력에 없는 출처 id: {', '.join(sorted(unknown))}"], unknown=sorted(unknown))
    outlets: set[int] = set()
    for sid in cited:
        outlets.update(ctx.docs[sid].get("outlet_ids") or [])
    available: set[int] = set()
    for d in ctx.docs.values():
        available.update(d.get("outlet_ids") or [])
    if len(outlets) < 2:
        # 입력 자체에 매체가 2곳 미만이면 재생성해도 해결되지 않는다
        action = "discard" if len(available) < 2 else "regen"
        return fail(ID, [f"인용한 매체가 {len(outlets)}곳 (2곳 이상 필요)"], action=action,
                    outlets=sorted(outlets), available=len(available))
    return ok(ID, outlets=sorted(outlets))
