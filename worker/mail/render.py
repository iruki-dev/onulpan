"""이메일 조간 렌더링. editions에 기록된 지면을 그대로 옮긴다 (웹과 같은 지면)."""
from __future__ import annotations

import html
import os
from dataclasses import dataclass

import psycopg

from .tokens import sign

SECTION_KO = {"politics": "정치", "economy": "경제", "society": "사회", "world": "국제", "scitech": "과학기술",
              "culture": "문화", "none": "기타"}
NOTICE_KO = {
    "collection_delayed": "밤사이 새 소식 수집이 지연되었습니다. 최근 72시간의 글로 지면을 채웠습니다.",
    "front_fallback": "오늘은 1면 후보가 부족해 전날 1면 주제의 종합 글로 채웠습니다.",
}


def site_url() -> str:
    return os.environ.get("SITE_URL", "http://localhost:3000").rstrip("/")


@dataclass
class RenderedEmail:
    subject: str
    html: str
    text: str
    unsubscribe_url: str


def _paras(body: str) -> list[str]:
    return [p.strip() for p in body.split("\n\n") if p.strip()]


# 디자인 토큰 (웹 globals.css와 같은 값)
INK, INK2, INK3, LINE, FILL, ACCENT = "#191F28", "#4E5968", "#6B7684", "#E5E8EB", "#F2F4F6", "#0B6E69"
SANS = "'IBM Plex Sans KR','Apple SD Gothic Neo','Malgun Gothic',sans-serif"
SERIF = "Hahmlet,'Noto Serif KR','Apple SD Gothic Neo',serif"


def render_edition(conn: psycopg.Connection, edition_id: int) -> RenderedEmail:
    ed = conn.execute(
        "SELECT e.*, u.email FROM editions e JOIN users u ON u.id = e.user_id WHERE e.id = %s", (edition_id,)
    ).fetchone()
    seqs = [x["seq"] for x in ed["slots"] if "seq" in x]
    posts = {r["seq"]: r for r in conn.execute(
        """SELECT p.seq, p.kind::text AS kind, p.section::text AS section, p.slug, p.title, p.summary, p.body_md, p.meta,
                  p.char_count,
                  COALESCE((p.meta->'cluster'->>'n_outlets')::int,
                           (SELECT count(DISTINCT s.outlet_id) FROM post_sources s WHERE s.post_seq = p.seq)) AS n_outlets
           FROM posts p WHERE p.seq = ANY(%s)""",
        (seqs,),
    ).fetchall()}
    base = site_url()
    d = ed["edition_date"]
    date_str = f"{d.month}월 {d.day}일"
    weekday = "월화수목금토일"[d.weekday()]
    unsub = f"{base}/unsubscribe?token={sign('unsub', str(ed['user_id']))}"
    web = f"{base}/e/{edition_id}?utm_source=email"
    E = html.escape

    def slot(name: str) -> list[dict]:
        return [posts[x["seq"]] for x in ed["slots"] if x["slot"] == name and x.get("seq") in posts]

    catchup, front, issues, briefs = slot("catchup"), slot("front"), slot("issue"), slot("brief")
    sec_items, background, culture = slot("section"), slot("background"), slot("culture")
    counted = catchup + front + issues + sec_items + background + culture
    minutes = sum(max(1, round((p["char_count"] or 0) / 550)) for p in counted) + -(-len(briefs) * 130 // 550)
    n_total = len(counted) + len(briefs)

    h: list[str] = []
    t: list[str] = []
    band = f'<div style="height:10px;background:{FILL}"></div>'

    def section_title(label: str, mb: int = 16) -> str:
        return f'<div style="font-size:18px;font-weight:700;margin-bottom:{mb}px">{E(label)}</div>'

    def link(url: str, text: str, style: str = "") -> str:
        return f'<a href="{url}" style="color:{INK};text-decoration:none;{style}">{E(text)}</a>'

    h.append(f'<div style="background:{FILL};padding:32px 12px;font-family:{SANS};color:{INK};word-break:keep-all">'
             f'<div style="max-width:600px;margin:0 auto;background:#FFFFFF;border-radius:16px;overflow:hidden">')
    h.append(f'<div style="padding:36px 28px 28px">'
             f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
             f'<td style="font-family:{SERIF};font-size:28px;font-weight:700;letter-spacing:-0.02em">오늘판</td>'
             f'<td align="right"><a href="{web}" style="font-size:13px;color:{INK3}">웹에서 보기</a></td></tr></table>'
             f'<div style="margin-top:20px;font-size:14px;color:{INK3}">{date_str} {weekday}요일 · {n_total}편 · {minutes}분</div>')
    t.append(f"오늘판 {date_str} {weekday}요일 · {n_total}편 · {minutes}분\n웹에서 보기: {web}\n")
    for x in ed["slots"]:
        if x["slot"] == "notice":
            msg = NOTICE_KO.get(x["code"], x["code"])
            h.append(f'<div style="margin-top:8px;font-size:14px;color:{INK2}">{E(msg)}</div>')
            t.append(msg)
    h.append("</div>")

    if catchup:
        h.append(f'<div style="padding:0 28px 12px"><div style="height:1px;background:{LINE}"></div>'
                 f'<div style="padding:28px 0 4px">{section_title("그동안의 흐름", 4)}</div>')
        t.append("\n■ 그동안의 흐름\n")
        for p in catchup:
            h.append(f'<p style="margin:0;padding:12px 0;font-size:15px;line-height:1.55">'
                     f'{link(base + "/p/" + str(p["seq"]), p["title"], "font-weight:600")} '
                     f'<span style="color:{INK3}">{E(p["summary"])}</span></p>')
            t.append(f"· {p['title']} — {p['summary']}")
        h.append("</div>")

    if front:
        h.append(f'<div style="padding:0 28px"><div style="height:1px;background:{LINE}"></div>'
                 f'<div style="padding:28px 0 8px;font-size:18px;font-weight:700">1면</div>')
        t.append("\n■ 1면\n")
        for i, p in enumerate(front):
            url = f"{base}/p/{p['seq']}"
            last = i == len(front) - 1
            border = "" if last else f"border-bottom:1px solid {LINE};"
            size = "24px;line-height:1.4" if i == 0 else "22px;line-height:1.42"
            h.append(f'<div style="padding:{16 if i == 0 else 24}px 0 28px;{border}">'
                     f'<div style="font-size:13px;font-weight:600;margin-bottom:8px">'
                     f'<span style="color:{INK3}">{i + 1:02d}</span>&#160;&#160;'
                     f'<span style="color:{ACCENT}">{E(SECTION_KO.get(p["section"], ""))}</span></div>'
                     f'<h2 style="margin:0 0 12px;font-family:{SERIF};font-size:{size}">{link(url, p["title"])}</h2>')
            t.append(f"{i + 1:02d} {p['title']}")
            for j, para in enumerate(_paras(p["body_md"])[: 2 if i == 0 else 1]):
                h.append(f'<p style="margin:0 0 12px;font-size:16px;line-height:1.8">{E(para)}</p>')
                t.append(para)
            h.append(f'<div style="margin-top:14px;font-size:13px;color:{INK3}">언론사 {p["n_outlets"]}곳 · '
                     f'<a href="{url}#sources" style="color:{INK3}">출처</a></div></div>')
            t.append(f"언론사 {p['n_outlets']}곳 · {url}\n")
        h.append("</div>")

    for p in issues:
        url = f"{base}/p/{p['seq']}"
        sec = p["meta"].get("sections") or {}
        h.append(band + f'<div style="padding:28px 28px">{section_title("오늘의 쟁점")}'
                 f'<h2 style="margin:0 0 16px;font-family:{SERIF};font-size:22px;line-height:1.42">'
                 f'{link(url, sec.get("question") or p["title"])}</h2>')
        t.append(f"\n■ 오늘의 쟁점\n{sec.get('question') or p['title']}")
        positions = sec.get("positions", [])[:3]
        if positions:
            w = 100 // len(positions)
            cells = []
            for k, pos in enumerate(positions):
                pad = "14px 16px 4px 0" if k == 0 else "14px 16px 4px 16px"
                if k == len(positions) - 1 and k > 0:
                    pad = "14px 0 4px 16px"
                bl = f"border-left:1px solid {LINE};" if k > 0 else ""
                cells.append(f'<td valign="top" width="{w}%" style="padding:{pad};{bl}font-size:15px;line-height:1.6">'
                             f'<strong style="display:block;margin-bottom:4px">{E(pos.get("holder", ""))}</strong>'
                             f'<span style="color:{INK2}">{E(pos.get("claim", ""))}</span></td>')
                t.append(f"- {pos.get('holder', '')}: {pos.get('claim', '')}")
            h.append(f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
                     f'style="border-top:1px solid {LINE}"><tr>{"".join(cells)}</tr></table>')
        h.append(f'<a href="{url}" style="display:inline-block;margin-top:18px;font-size:15px;font-weight:600;'
                 f'color:{INK2};text-decoration:none">근거와 남은 질문 &#8250;</a></div>')
        t.append(f"근거와 남은 질문: {url}")

    if briefs:
        h.append(band + f'<div style="padding:28px 28px 8px">{section_title("단신", 4)}')
        t.append("\n■ 단신\n")
        for p in briefs:
            h.append(f'<p style="margin:0;padding:12px 0;font-size:15px;line-height:1.55">'
                     f'{link(base + "/p/" + str(p["seq"]), p["title"], "font-weight:600")} '
                     f'<span style="color:{INK3}">{E(p["summary"])}</span></p>')
            t.append(f"· {p['title']} — {p['summary']} {base}/p/{p['seq']}")
        h.append("</div>")

    rest: list[str] = []
    for key in ("politics", "economy", "society", "world", "scitech", "culture", "none"):
        if any(p["section"] == key for p in sec_items):
            rest.append(SECTION_KO[key])
    if background:
        rest.append("배경")
    if culture:
        rest.append("교양")
    cta = (" · ".join(rest) + " 이어 읽기") if rest else "웹에서 보기"
    h.append(f'<div style="padding:{20 if briefs else 28}px 28px 36px"><a href="{web}" style="display:block;padding:16px;'
             f'border-radius:14px;background:{FILL};text-align:center;font-size:15px;font-weight:600;color:{INK};'
             f'text-decoration:none">{E(cta)}</a></div>')
    t.append(f"\n{cta}: {web}")
    for p in sec_items + background + culture:
        t.append(f"· {p['title']} {base}/p/{p['seq']}")

    how = f"{base}/front/{ed['edition_date']}"
    h.append(f'</div><div style="max-width:600px;margin:0 auto;padding:24px 8px;font-size:12px;line-height:1.8;'
             f'color:{INK3};text-align:center">AI가 여러 언론 보도를 종합해 씁니다<br>'
             f'<a href="{how}" style="color:{INK3}">1면 선정 기준</a> · '
             f'<a href="{base}/principles" style="color:{INK3}">편집 원칙</a> · '
             f'<a href="{base}/settings" style="color:{INK3}">설정</a> · '
             f'<a href="{unsub}" style="color:{INK3}">수신 거부</a></div></div>')
    t.append(f"\nAI가 여러 언론 보도를 종합해 씁니다.\n1면 선정 기준: {how}\n편집 원칙: {base}/principles\n"
             f"설정: {base}/settings\n수신 거부: {unsub}")
    subject = f"[오늘판 {date_str}] " + (front[0]["title"] if front else "오늘의 조간")
    return RenderedEmail(subject=subject, html="".join(h), text="\n".join(t), unsubscribe_url=unsub)
