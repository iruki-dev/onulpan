"""V6 인용: quotes[].text가 원문에 공백 정규화 후 그대로 있고, 같은 원문에 발언자 이름이 있는지.
한 글에 최대 2회, 각 40자 이내. 본문의 따옴표 구간도 인용 목록이나 원문에 있어야 한다."""
from __future__ import annotations

import re

from ..base import Context, RuleResult, fail, ok, quote_spans, skip, squash

ID = "V6"


def _speaker_tokens(speaker: str) -> list[str]:
    toks = [t for t in re.split(r"[\s·,()]+", speaker or "") if len(t) >= 2]
    return toks or [speaker]


def check(ctx: Context) -> RuleResult:
    if ctx.draft is None:
        return skip(ID, "parse_failed")
    v = ctx.s["verify"]
    quotes = ctx.draft.get("quotes") or []
    msgs = []
    if len(quotes) > v["max_quotes"]:
        msgs.append(f"직접 인용은 최대 {v['max_quotes']}회: 현재 {len(quotes)}회")
    for q in quotes:
        text, speaker, sid = q.get("text", ""), q.get("speaker", ""), q.get("source_id", "")
        if len(text) > v["quote_max_chars"]:
            msgs.append(f"인용이 {v['quote_max_chars']}자를 넘음: {text[:20]}…")
        doc = ctx.docs.get(sid)
        if doc is None:
            msgs.append(f"인용 출처 id가 입력에 없음: {sid}")
            continue
        dt = squash(doc["text"])
        if squash(text) not in dt:
            msgs.append(f"원문({sid})에 그대로 있지 않은 인용: {text[:30]}")
        if not any(squash(t) in dt for t in _speaker_tokens(speaker)):
            msgs.append(f"원문({sid})에 발언자가 없음: {speaker}")
    if ctx.kind == "culture" or not ctx.docs:
        return fail(ID, msgs) if msgs else ok(ID, n_quotes=len(quotes))
    listed = [squash(q.get("text", "")) for q in quotes]
    src = squash(ctx.source_text)
    for span in quote_spans(ctx.body):
        k = squash(span)
        if len(k) < 6:
            continue
        if not any(k in l or l in k for l in listed if l) and k not in src:
            msgs.append(f"출처가 확인되지 않는 따옴표 구간: {span[:30]}")
    return fail(ID, msgs) if msgs else ok(ID, n_quotes=len(quotes))
