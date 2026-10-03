"""한국어 처리 도우미: kiwipiepy 형태소 분석, 고유명사 추출, 어절·문장 분리, 텍스트 정규화."""
from __future__ import annotations

import re
import threading
import unicodedata
from functools import lru_cache

_kiwi = None
_kiwi_lock = threading.Lock()


def kiwi():
    global _kiwi
    if _kiwi is None:
        with _kiwi_lock:
            if _kiwi is None:
                from kiwipiepy import Kiwi

                _kiwi = Kiwi()
    return _kiwi


_WS = re.compile(r"\s+")
_QUOTES = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'", "「": '"', "」": '"', "『": '"', "』": '"'})


def normalize_ws(text: str) -> str:
    return _WS.sub(" ", unicodedata.normalize("NFC", text or "")).strip()


def normalize_quotes(text: str) -> str:
    return (text or "").translate(_QUOTES)


def eojeols(text: str) -> list[str]:
    """어절(띄어쓰기 단위). 문장부호는 떼어 비교한다."""
    out = []
    for w in normalize_ws(normalize_quotes(text)).split(" "):
        w = w.strip(".,!?;:\"'()[]{}<>…·~-")
        if w:
            out.append(w)
    return out


def morphemes(text: str) -> list[str]:
    """내용 형태소(명사·동사·형용사·숫자·외국어). SimHash의 단위."""
    keep = ("NN", "VV", "VA", "SN", "SL", "SH", "XR", "MAG")
    return [t.form for t in kiwi().tokenize(text or "") if t.tag.startswith(keep)]


@lru_cache(maxsize=4096)
def _nnps_cached(text: str) -> tuple[str, ...]:
    out: list[str] = []
    toks = kiwi().tokenize(text)
    i = 0
    while i < len(toks):
        t = toks[i]
        if t.tag == "NNP":
            # 붙어 있는 NNP+NNP(예: 한국+은행)는 하나로 합친다
            form, end = t.form, t.start + t.len
            j = i + 1
            while j < len(toks) and toks[j].tag in ("NNP",) and toks[j].start == end:
                form += toks[j].form
                end = toks[j].start + toks[j].len
                j += 1
            if len(form) >= 2:
                out.append(form)
            i = j
        else:
            i += 1
    return tuple(dict.fromkeys(out))


def proper_nouns(text: str) -> list[str]:
    return list(_nnps_cached(normalize_ws(text or "")))


_SENT_END = re.compile(r"(?<=[.!?。])\s+|(?<=다\.)\s*|\n+")


def sentences(text: str) -> list[str]:
    """문장 분리. kiwi의 split_into_sents를 쓰고, 실패하면 정규식으로 나눈다."""
    text = (text or "").strip()
    if not text:
        return []
    try:
        sents = [s.text.strip() for s in kiwi().split_into_sents(text)]
    except Exception:  # pragma: no cover - kiwi 내부 오류 대비
        sents = [s.strip() for s in _SENT_END.split(text)]
    return [s for s in sents if len(s) >= 2]


def strip_josa(word: str) -> str:
    """어절 끝의 조사를 떼어 낸다. ‘삼성전자는’ → ‘삼성전자’"""
    toks = kiwi().tokenize(word)
    if not toks:
        return word
    end = len(word)
    for t in reversed(toks):
        if t.tag.startswith(("J", "E", "XS", "VCP")):
            end = t.start
        else:
            break
    return word[:end] if end > 0 else word


def char_count(text: str) -> int:
    """분량은 공백을 포함한 글자 수로 센다(마크다운 문단 구분 줄바꿈 제외)."""
    return len(re.sub(r"\n+", "", text or ""))
