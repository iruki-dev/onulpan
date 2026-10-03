"""2단계 중복 제거: kiwipiepy 형태소 기준 3-shingle SimHash(64비트)."""
from __future__ import annotations

import hashlib

from ..nlp import morphemes


def _h64(s: str) -> int:
    return int.from_bytes(hashlib.blake2b(s.encode("utf-8"), digest_size=8).digest(), "big")


def simhash(text: str, shingle: int = 3) -> int:
    toks = morphemes(text)
    if len(toks) < shingle:
        toks = toks + [""] * (shingle - len(toks))
    acc = [0] * 64
    for i in range(len(toks) - shingle + 1):
        h = _h64("\x1f".join(toks[i : i + shingle]))
        for b in range(64):
            acc[b] += 1 if (h >> b) & 1 else -1
    value = 0
    for b in range(64):
        if acc[b] > 0:
            value |= 1 << b
    return to_signed(value)


def to_signed(v: int) -> int:
    """Postgres bigint에 넣기 위해 부호 있는 64비트로."""
    return v - (1 << 64) if v >= (1 << 63) else v


def hamming(a: int, b: int) -> int:
    return bin((a ^ b) & ((1 << 64) - 1)).count("1")
