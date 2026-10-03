"""V4 날짜: 절대 날짜는 원문과 대조. 상대 날짜(어제, 지난주, 오늘)는 금지. 조간은 다음 날 읽히기 때문."""
from __future__ import annotations

import re
from datetime import datetime
from functools import lru_cache

from ...settings import RULES_DIR
from ..base import Context, RuleResult, fail, ok, skip
from ..numbers import extract_dates

ID = "V4"


@lru_cache(maxsize=1)
def relative_patterns() -> list[re.Pattern]:
    pats = []
    for line in (RULES_DIR / "relative_dates.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            pats.append(re.compile(line))
    return pats


def _published(ctx: Context) -> list[datetime]:
    out = []
    for d in ctx.docs.values():
        try:
            out.append(datetime.fromisoformat(d.get("published", "")))
        except ValueError:
            pass
    return out


def check(ctx: Context) -> RuleResult:
    if ctx.draft is None:
        return skip(ID, "parse_failed")
    msgs: list[str] = []
    text = ctx.all_text
    for p in relative_patterns():
        for m in p.finditer(text):
            msgs.append(f"상대 날짜 금지: ‘{m.group(0)}’")
    if ctx.kind != "culture":
        src = ctx.source_text
        src_dates = extract_dates(src)
        pubs = _published(ctx)
        md = {(x.month, x.day) for x in src_dates if x.month}
        days = {x.day for x in src_dates if x.day} | {p.day for p in pubs}
        md |= {(p.month, p.day) for p in pubs}
        years = {x.year for x in src_dates if x.year} | {p.year for p in pubs}
        for dm in extract_dates(text):
            if dm.month and dm.day and (dm.month, dm.day) not in md:
                msgs.append(f"원문에 없는 날짜: {dm.raw}")
            elif dm.month is None and dm.day and dm.day not in days:
                msgs.append(f"원문에 없는 날짜: {dm.raw}")
            if dm.year and dm.year not in years and str(dm.year) not in src:
                msgs.append(f"원문에 없는 연도: {dm.raw}")
    return fail(ID, list(dict.fromkeys(msgs))) if msgs else ok(ID)
