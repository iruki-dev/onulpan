"""V1 스키마: JSON 파싱 + 필드·길이 검사 (제목 36자, 요약 80자, 본문 분량 범위)."""
from __future__ import annotations

import re

from ...generate.schema import REQUIRED_FIELDS, SECTIONS
from ...nlp import char_count
from ..base import Context, RuleResult, fail, ok

ID = "V1"
TITLE_BANNED = re.compile(r"[\"'“”‘’?!？！]")


def check(ctx: Context) -> RuleResult:
    if ctx.draft is None:
        return fail(ID, [f"JSON 파싱 실패: {ctx.parse_error or '출력 없음'}"])
    d = ctx.draft
    L = ctx.s["verify"]["lengths"]
    msgs: list[str] = []
    missing = [f for f in REQUIRED_FIELDS[ctx.kind] if f not in d]
    if missing:
        msgs.append(f"필드 누락: {', '.join(missing)}")
    if d.get("kind") != ctx.kind:
        msgs.append(f"kind가 '{ctx.kind}'가 아님: {d.get('kind')!r}")
    if d.get("section") not in SECTIONS:
        msgs.append(f"section 값이 잘못됨: {d.get('section')!r}")
    for f in ("title", "summary", "slug_suggestion"):
        if f in d and not isinstance(d[f], str):
            msgs.append(f"{f}는 문자열이어야 함")
    for f in ("facts", "quotes", "terms", "conflicts"):
        if f in d and not isinstance(d[f], list):
            msgs.append(f"{f}는 배열이어야 함")
    if msgs:
        return fail(ID, msgs)

    title, summary = d["title"].strip(), d["summary"].strip()
    if not title or len(title) > L["title"]:
        msgs.append(f"제목은 1~{L['title']}자: 현재 {len(title)}자")
    if TITLE_BANNED.search(title):
        msgs.append("제목에 따옴표·물음표·느낌표를 쓰지 않음")
    if not summary or len(summary) > L["summary"]:
        msgs.append(f"요약은 1~{L['summary']}자: 현재 {len(summary)}자")
    if "\n" in summary:
        msgs.append("요약은 한 문장")
    if not d.get("slug_suggestion", "").strip():
        msgs.append("slug_suggestion이 비어 있음")
    if ctx.kind == "issue":
        sec = d.get("sections") or {}
        if not isinstance(sec, dict) or not sec.get("question") or not sec.get("positions"):
            msgs.append("쟁점 정리는 sections.question과 sections.positions가 필요함")
        elif len(sec["positions"]) < 2:
            msgs.append("쟁점 정리는 입장이 2개 이상이어야 함")
    else:
        body = d.get("body_md") or ""
        if re.search(r"^\s*(#|[-*] |\d+\. )", body, re.M) or "**" in body:
            msgs.append("본문에 제목·목록·굵게를 쓰지 않음")
    lo, hi = L["body"][ctx.kind]
    tol = L.get("tolerance", 0)
    n = char_count(ctx.body)
    if not (lo * (1 - tol) <= n <= hi * (1 + tol)):
        msgs.append(f"본문 분량 {lo}~{hi}자 범위 밖: 현재 {n}자")
    facts = d.get("facts") or []
    if not facts:
        msgs.append("facts가 비어 있음")
    for i, f in enumerate(facts):
        if not isinstance(f, dict) or not isinstance(f.get("text"), str) or not isinstance(f.get("source_ids"), list):
            msgs.append(f"facts[{i}] 형식이 잘못됨")
    return fail(ID, msgs) if msgs else ok(ID, body_chars=n)
