"""2단계 정규화: 기자명·저작권 문구·광고 문구 제거."""
from __future__ import annotations

import re
from functools import lru_cache

from ..nlp import normalize_ws
from ..settings import RULES_DIR


@lru_cache(maxsize=1)
def _patterns() -> list[re.Pattern]:
    out = []
    for line in (RULES_DIR / "boilerplate.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(re.compile(line, re.M))
    return out


def clean_body(text: str) -> str:
    if not text:
        return ""
    lines = []
    for line in text.replace("\r", "").split("\n"):
        for p in _patterns():
            line = p.sub("", line)
        line = normalize_ws(line)
        if len(line) >= 2:
            lines.append(line)
    return "\n".join(lines)


def lead_of(title: str, body: str, max_chars: int) -> str:
    """임베딩 입력: 제목 + 리드(본문 앞부분)."""
    return (normalize_ws(title) + "\n" + (body or ""))[:max_chars]
