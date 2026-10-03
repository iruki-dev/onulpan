"""V10 사실 대응: 본문 문장마다 facts[].text 중 하나와 임베딩 유사도 0.75 이상."""
from __future__ import annotations

import numpy as np

from ...nlp import sentences
from ..base import Context, RuleResult, fail, ok, skip

ID = "V10"


def check(ctx: Context) -> RuleResult:
    if ctx.draft is None:
        return skip(ID, "parse_failed")
    if ctx.embed is None:
        return skip(ID, "임베더 없음")
    v = ctx.s["verify"]
    threshold = v["fact_similarity"] if ctx.embedder_name == "bge-m3" else v["fact_similarity_hashing"]
    facts = [f.get("text", "") for f in ctx.draft.get("facts") or [] if isinstance(f, dict) and f.get("text")]
    if ctx.kind == "issue":
        sec = ctx.draft.get("sections") or {}
        sents = list(sec.get("facts") or []) + [p.get("claim", "") for p in sec.get("positions") or []]
        sents = [x for s in sents for x in sentences(s)]
    else:
        sents = sentences(ctx.body)
    sents = [s for s in sents if len(s) >= 10]
    if not sents:
        return ok(ID)
    if not facts:
        return fail(ID, ["facts가 비어 있어 본문 문장을 대응시킬 수 없음"])
    S = np.asarray(ctx.embed(sents))
    F = np.asarray(ctx.embed(facts))
    sims = S @ F.T
    best = sims.max(axis=1)
    weak = [(s, float(b)) for s, b in zip(sents, best) if b < threshold]
    if weak:
        return fail(ID, [f"facts에 대응하는 사실이 없는 문장({b:.2f}): {s[:40]}" for s, b in weak],
                    threshold=threshold, weak=len(weak))
    return ok(ID, threshold=threshold, min_similarity=round(float(best.min()), 3))
