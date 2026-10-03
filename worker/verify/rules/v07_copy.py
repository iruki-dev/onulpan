"""V7 복제율: 원문 각각과 가장 긴 공통 어절 열 7어절 이하, 5-gram 겹침 비율 15% 미만 (인용 구간 제외)."""
from __future__ import annotations

from ...nlp import eojeols
from ..base import Context, RuleResult, fail, ok, skip, without_quotes

ID = "V7"


def longest_common_run(a: list[str], b: list[str]) -> int:
    if not a or not b:
        return 0
    best = 0
    prev = [0] * (len(b) + 1)
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        ai = a[i - 1]
        for j in range(1, len(b) + 1):
            if ai == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
        prev = cur
    return best


def ngram_ratio(a: list[str], b: list[str], n: int) -> float:
    ga = {tuple(a[i : i + n]) for i in range(len(a) - n + 1)}
    if not ga:
        return 0.0
    gb = {tuple(b[i : i + n]) for i in range(len(b) - n + 1)}
    return len(ga & gb) / len(ga)


def check(ctx: Context) -> RuleResult:
    if ctx.draft is None:
        return skip(ID, "parse_failed")
    if not ctx.has_raw_sources:
        return skip(ID, "원문 기사 입력 없음 (우리 글을 입력으로 쓰는 종류)")
    v = ctx.s["verify"]
    quotes = [q.get("text", "") for q in ctx.draft.get("quotes") or []]
    body = eojeols(without_quotes(ctx.body, quotes))
    msgs, per = [], {}
    for sid, d in ctx.docs.items():
        if d.get("kind") != "raw":
            continue
        src = eojeols(without_quotes(d["text"], quotes))
        run = longest_common_run(body, src)
        ratio = ngram_ratio(body, src, v["copy_ngram"])
        per[sid] = {"run": run, "ratio": round(ratio, 3)}
        if run > v["copy_max_run"]:
            msgs.append(f"원문({sid})과 {run}어절 연속 일치 (최대 {v['copy_max_run']})")
        if ratio >= v["copy_ngram_ratio"]:
            msgs.append(f"원문({sid})과 {v['copy_ngram']}-gram 겹침 {ratio:.0%} (15% 미만이어야 함)")
    return fail(ID, msgs, per_source=per) if msgs else ok(ID, per_source=per)
