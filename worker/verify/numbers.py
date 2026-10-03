"""숫자·날짜 추출과 정규화 (V3, V4, V9).

1만2천 = 12,000, 1조 2000억 = 1.2조, 3.5% = 3.5퍼센트, 세 명 = 3명.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..nlp import strip_josa

UNIT_ALIASES = {
    "%": "%", "％": "%", "퍼센트": "%", "프로": "%",
    "%p": "%p", "%포인트": "%p", "퍼센트포인트": "%p", "포인트": "p", "p": "p", "bp": "bp",
    "명": "명", "원": "원", "달러": "달러", "엔": "엔", "위안": "위안", "유로": "유로",
    "건": "건", "개": "개", "곳": "곳", "대": "대", "채": "채", "척": "척", "톤": "톤", "t": "톤",
    "kg": "kg", "㎏": "kg", "km": "km", "㎞": "km", "m": "m", "㎡": "㎡", "평": "평",
    "배": "배", "가구": "가구", "세대": "세대", "표": "표", "석": "석", "회": "회", "차례": "회", "번": "회",
    "살": "세", "세": "세", "개월": "개월", "시간": "시간", "분": "분", "초": "초", "주": "주",
    "년": "년", "월": "월", "일": "일", "시": "시", "마리": "마리", "가지": "가지", "개국": "개국", "명분": "명",
    "만": "", "억": "", "조": "",
}
_units_sorted = sorted((u for u in UNIT_ALIASES if u and u not in ("만", "억", "조")), key=len, reverse=True)
UNIT_RE = "|".join(re.escape(u) for u in _units_sorted)

MAG = {"천": 1e3, "백": 1e2, "만": 1e4, "억": 1e8, "조": 1e12}
_NUM = r"\d+(?:,\d{3})*(?:\.\d+)?"
# 숫자 덩어리: 12,000 | 3.5 | 1만2천 | 1조 2000억 | 2천
NUMBER_RE = re.compile(
    rf"(?<![\w.])((?:{_NUM}\s*(?:조|억|만|천|백)\s*)*{_NUM}(?:\s*(?:조|억|만|천|백))?)"
    rf"\s*({UNIT_RE})?",
)

NATIVE = {"한": 1, "두": 2, "세": 3, "네": 4, "다섯": 5, "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9, "열": 10,
          "스무": 20, "서른": 30, "마흔": 40, "쉰": 50}
NATIVE_RE = re.compile(r"(?<![가-힣])(한|두|세|네|다섯|여섯|일곱|여덟|아홉|열|스무|서른|마흔|쉰)\s?(명|곳|개|차례|번|가지|건|척|대|채|마리|가구|개국)")


@dataclass(frozen=True)
class Num:
    value: float
    unit: str
    raw: str
    start: int
    context: str = ""   # 숫자 앞 어절(조사 제거) — V9 충돌 탐지용


def parse_korean_number(s: str) -> float | None:
    s = s.replace(" ", "")
    total = 0.0
    cur = ""
    section = 0.0  # 만·억·조 아래 단위 누적 (천·백)
    try:
        for ch in s:
            if ch.isdigit() or ch in ".,":
                if ch != ",":
                    cur += ch
            elif ch in ("천", "백"):
                section += (float(cur) if cur else 1.0) * MAG[ch]
                cur = ""
            elif ch in ("만", "억", "조"):
                section += float(cur) if cur else 0.0
                total += (section or 1.0) * MAG[ch]
                section, cur = 0.0, ""
            else:
                return None
        section += float(cur) if cur else 0.0
        return total + section
    except ValueError:
        return None


def _context_before(text: str, start: int) -> str:
    before = text[max(0, start - 30):start].rstrip()
    words = re.findall(r"[가-힣A-Za-z]+", before)
    if not words:
        return ""
    w = words[-1]
    return strip_josa(w) if len(w) > 1 else w


def extract_numbers(text: str, with_context: bool = False) -> list[Num]:
    out: list[Num] = []
    for m in NUMBER_RE.finditer(text or ""):
        raw_num, unit = m.group(1), m.group(2) or ""
        value = parse_korean_number(raw_num)
        if value is None:
            continue
        # 영문·한글에 붙은 숫자(코로나19, G20, 제2차)는 이름의 일부로 본다
        if m.start() > 0 and re.match(r"[A-Za-z가-힣]", text[m.start() - 1]):
            continue
        u = UNIT_ALIASES.get(unit, unit)
        ctx = _context_before(text, m.start()) if with_context else ""
        out.append(Num(round(value, 4), u, m.group(0).strip(), m.start(), ctx))
    for m in NATIVE_RE.finditer(text or ""):
        out.append(Num(float(NATIVE[m.group(1)]), UNIT_ALIASES.get(m.group(2), m.group(2)), m.group(0), m.start(),
                       _context_before(text, m.start()) if with_context else ""))
    return out


DATE_UNITS = {"년", "월", "일", "시", "분"}


def is_date_like(n: Num) -> bool:
    return n.unit in ("월", "일", "시", "분") or (n.unit == "년" and 1900 <= n.value <= 2100)


# ── 날짜 (V4) ──────────────────────────────────────────

FULL_DATE_RE = re.compile(r"(?:(\d{4})\s*년\s*)?(\d{1,2})\s*월\s*(\d{1,2})\s*일")
DAY_ONLY_RE = re.compile(r"(?<![\d월.])(?<!월\s)(\d{1,2})\s*일(?![간째])")
YEAR_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})\s*년")


@dataclass(frozen=True)
class DateMention:
    year: int | None
    month: int | None
    day: int | None
    raw: str


def extract_dates(text: str) -> list[DateMention]:
    out: list[DateMention] = []
    spans: list[tuple[int, int]] = []
    for m in FULL_DATE_RE.finditer(text):
        out.append(DateMention(int(m.group(1)) if m.group(1) else None, int(m.group(2)), int(m.group(3)), m.group(0)))
        spans.append(m.span())
    for m in DAY_ONLY_RE.finditer(text):
        if any(a <= m.start() < b for a, b in spans):
            continue
        out.append(DateMention(None, None, int(m.group(1)), m.group(0)))
    for m in YEAR_RE.finditer(text):
        if any(a <= m.start() < b for a, b in spans):
            continue
        out.append(DateMention(int(m.group(1)), None, None, m.group(0)))
    return out
