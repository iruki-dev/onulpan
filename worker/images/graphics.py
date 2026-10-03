"""자체 제작 그래픽. 원자료는 오늘판이 이미 쓴 글(언론 보도 종합)이고, 크레딧에 원자료 출처를 적는다.

이메일 클라이언트가 SVG를 막는 경우가 많아 PNG로 그린다. 한글 글꼴이 없으면 그리지 않는다.
"""
from __future__ import annotations

import io
import os
from datetime import datetime
from pathlib import Path

import psycopg

from ..timeutil import kst

# 디자인 토큰 (web/app/globals.css)
INK, INK2, INK3, ICON, LINE, FILL, ACCENT = "#191F28", "#4E5968", "#6B7684", "#B0B8C1", "#D1D6DB", "#F2F4F6", "#0B6E69"

FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-{w}.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-{w}.ttc",
    "/usr/share/fonts/truetype/nanum/NanumGothic{nw}.ttf",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
]


def font_path(bold: bool = False) -> str | None:
    env = os.environ.get("IMAGE_FONT_BOLD" if bold else "IMAGE_FONT")
    if env and Path(env).exists():
        return env
    for c in FONT_CANDIDATES:
        p = c.format(w="Bold" if bold else "Regular", nw="Bold" if bold else "")
        if Path(p).exists():
            return p
    return None


def _wrap(draw, text: str, font, width: int, max_lines: int = 2) -> list[str]:
    """어절 단위로 줄을 나눈다(낱말 중간에서 끊지 않는다). 한 어절이 한 줄보다 길 때만 글자 단위로."""
    fits = lambda t: draw.textlength(t, font=font) <= width  # noqa: E731
    lines: list[str] = []
    cur = ""
    for word in text.split():
        cand = f"{cur} {word}" if cur else word
        if fits(cand):
            cur = cand
            continue
        if cur:
            lines.append(cur)
        cur = word
        while not fits(cur):                      # 아주 긴 어절
            i = len(cur)
            while i > 1 and not fits(cur[:i]):
                i -= 1
            lines.append(cur[:i])
            cur = cur[i:]
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        last = lines[max_lines - 1]
        while last and not fits(last + "…"):
            last = last[:-1]
        lines = lines[:max_lines - 1] + [last.rstrip() + "…"]
    return lines


def timeline_png(title: str, events: list[tuple[datetime, str]], width: int = 1200) -> bytes | None:
    """주제의 흐름: 날짜와 글 제목을 세로선 위에 놓는다. 마지막(최신) 점만 강조색. 16:9 안에 가운데 정렬."""
    from PIL import Image, ImageDraw, ImageFont

    reg, bold = font_path(False), font_path(True)
    if not reg:
        return None
    fake_bold = bold is None or bold == reg               # 굵은 글꼴이 따로 없으면 획을 덧그린다
    bold = bold or reg
    sw = 1 if fake_bold else 0
    f_title, f_label = ImageFont.truetype(bold, 64), ImageFont.truetype(bold, 34)
    f_date, f_item = ImageFont.truetype(reg, 36), ImageFont.truetype(bold, 46)
    pad, line_x = 88, 104
    text_x = line_x + 56
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    rows = [(d, _wrap(probe, t, f_item, width - text_x - pad)) for d, t in events]
    row_h = [52 + 62 * len(lines) + 40 for _, lines in rows]
    content_h = 48 + 88 + 64 + sum(row_h) - 40
    height = max(round(width * 9 / 16), content_h + 2 * pad)
    im = Image.new("RGB", (width, height), FILL)
    dr = ImageDraw.Draw(im)
    y = (height - content_h) // 2
    dr.text((pad, y), "흐름", font=f_label, fill=ACCENT, stroke_width=sw, stroke_fill=ACCENT)
    dr.text((pad, y + 48), _wrap(dr, title, f_title, width - 2 * pad, 1)[0], font=f_title, fill=INK,
            stroke_width=sw, stroke_fill=INK)
    y += 48 + 88 + 64
    centers = [y + sum(row_h[:i]) + 22 for i in range(len(rows))]
    dr.line([(line_x, centers[0]), (line_x, centers[-1])], fill=LINE, width=4)
    for i, ((d, lines), cy) in enumerate(zip(rows, centers)):
        last = i == len(rows) - 1
        top = cy - 22
        dr.text((text_x, top), f"{d.month}월 {d.day}일", font=f_date, fill=ACCENT if last else INK3)
        color = INK if last else INK2
        for j, ln in enumerate(lines):
            dr.text((text_x, top + 52 + j * 62), ln, font=f_item, fill=color, stroke_width=sw, stroke_fill=color)
        r = 15 if last else 11
        dr.ellipse([line_x - r, cy - r, line_x + r, cy + r], fill=ACCENT if last else ICON,
                   outline=FILL, width=5)
    out = io.BytesIO()
    im.save(out, "PNG", optimize=True)
    return out.getvalue()


def timeline_for_slug(conn: psycopg.Connection, slug: str, upto_seq: int, max_events: int = 6) -> dict | None:
    """같은 주제의 글이 서로 다른 날짜로 2개 이상일 때만 그린다. 원자료(보도한 언론사)를 함께 돌려준다."""
    rows = conn.execute(
        """SELECT DISTINCT ON (kst_date(created_at)) seq, title, created_at FROM posts
           WHERE slug = %s AND created_at <= (SELECT created_at FROM posts WHERE seq = %s)
             AND kind IN ('fact','synthesis','issue','correction')
           ORDER BY kst_date(created_at), seq DESC""",
        (slug, upto_seq),
    ).fetchall()
    if len(rows) < 2:
        return None
    rows = rows[-max_events:]
    name = conn.execute("SELECT display_name FROM slugs WHERE slug = %s", (slug,)).fetchone()
    outlets = [r["name"] for r in conn.execute(
        """SELECT o.name, count(*) AS n FROM post_sources s JOIN outlets o ON o.id = s.outlet_id
           WHERE s.post_seq = ANY(%s) GROUP BY o.name ORDER BY n DESC, o.name LIMIT 3""",
        ([r["seq"] for r in rows],),
    ).fetchall()]
    title = name["display_name"] if name else slug.replace("-", " ")
    png = timeline_png(title, [(kst(r["created_at"]), r["title"]) for r in rows])
    if png is None:
        return None
    data = ", ".join(outlets) + (" 등 보도 종합" if outlets else "") or "오늘판 기사"
    return {"png": png, "title": f"{title} 흐름", "alt": f"{title}의 주요 흐름을 날짜순으로 정리한 그래픽",
            "data": data, "seqs": [r["seq"] for r in rows]}
