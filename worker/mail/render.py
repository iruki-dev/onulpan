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


def render_edition(conn: psycopg.Connection, edition_id: int) -> RenderedEmail:
    ed = conn.execute(
        "SELECT e.*, u.email FROM editions e JOIN users u ON u.id = e.user_id WHERE e.id = %s", (edition_id,)
    ).fetchone()
    seqs = [x["seq"] for x in ed["slots"] if "seq" in x]
    posts = {r["seq"]: r for r in conn.execute(
        """SELECT p.seq, p.kind::text AS kind, p.section::text AS section, p.slug, p.title, p.summary, p.body_md, p.meta,
                  (SELECT count(*) FROM post_sources s WHERE s.post_seq = p.seq) AS n_sources
           FROM posts p WHERE p.seq = ANY(%s)""",
        (seqs,),
    ).fetchall()}
    base = site_url()
    date_str = f"{ed['edition_date'].month}월 {ed['edition_date'].day}일"
    unsub = f"{base}/unsubscribe?token={sign('unsub', str(ed['user_id']))}"
    web = f"{base}/e/{edition_id}?utm_source=email"

    h: list[str] = []
    t: list[str] = []
    E = html.escape

    def head(label: str) -> None:
        h.append(f'<h2 style="font-size:13px;letter-spacing:.08em;color:#6b6257;border-top:2px solid #1d1a16;'
                 f'padding-top:10px;margin:32px 0 12px">{E(label)}</h2>')
        t.append(f"\n■ {label}\n")

    def article(p: dict, full: bool = True) -> None:
        url = f"{base}/p/{p['seq']}"
        h.append(f'<h3 style="font-size:20px;line-height:1.35;margin:18px 0 6px"><a href="{url}" '
                 f'style="color:#1d1a16;text-decoration:none">{E(p["title"])}</a></h3>')
        t.append(p["title"])
        if p["kind"] == "issue" and p["meta"].get("sections"):
            sec = p["meta"]["sections"]
            h.append(f'<p style="margin:6px 0;font-weight:600">{E(sec.get("question", ""))}</p>')
            for pos in sec.get("positions", []):
                h.append(f'<p style="margin:6px 0"><b>{E(pos.get("holder",""))}</b> — {E(pos.get("claim",""))}'
                         f'<br><span style="color:#6b6257">근거: {E(pos.get("grounds",""))}</span></p>')
                t.append(f"- {pos.get('holder','')}: {pos.get('claim','')} (근거: {pos.get('grounds','')})")
        elif full:
            for para in _paras(p["body_md"]):
                h.append(f'<p style="font-size:16px;line-height:1.75;margin:0 0 12px">{E(para)}</p>')
                t.append(para)
        else:
            h.append(f'<p style="font-size:15px;line-height:1.7;margin:0 0 8px">{E(p["summary"])}</p>')
            t.append(p["summary"])
        h.append(f'<p style="font-size:12px;color:#8a8175;margin:0 0 14px">AI가 언론 보도 {p["n_sources"]}건을 종합해 씀 · '
                 f'<a href="{url}#sources" style="color:#8a8175">출처 보기</a></p>')
        t.append(f"(AI가 언론 보도 {p['n_sources']}건을 종합해 씀) {url}\n")

    h.append('<div style="max-width:640px;margin:0 auto;padding:24px 18px;font-family:-apple-system,\'Apple SD Gothic Neo\','
             '\'Noto Sans KR\',sans-serif;color:#1d1a16;background:#fbf8f2">')
    h.append(f'<p style="font-size:12px;color:#6b6257;margin:0">{date_str} 조간 · <a href="{web}" style="color:#6b6257">웹에서 보기</a></p>')
    h.append('<h1 style="font-family:Georgia,serif;font-size:34px;margin:6px 0 4px">오늘판</h1>')
    t.append(f"오늘판 {date_str} 조간\n웹에서 보기: {web}\n")

    for x in ed["slots"]:
        if x["slot"] == "notice":
            msg = NOTICE_KO.get(x["code"], x["code"])
            h.append(f'<p style="background:#efe7d6;padding:10px 12px;font-size:14px">{E(msg)}</p>')
            t.append(f"[알림] {msg}")

    groups = [("catchup", "그동안의 주요 흐름", True), ("front", "1면", True), ("issue", "오늘의 쟁점", True)]
    for slot, label, full in groups:
        items = [posts[x["seq"]] for x in ed["slots"] if x["slot"] == slot and x["seq"] in posts]
        if items:
            head(label)
            for p in items:
                article(p, full)
    sec_items = [posts[x["seq"]] for x in ed["slots"] if x["slot"] == "section" and x["seq"] in posts]
    for sec in ("politics", "economy", "society", "world", "scitech", "culture", "none"):
        items = [p for p in sec_items if p["section"] == sec]
        if items:
            head(SECTION_KO[sec])
            for p in items:
                article(p)
    briefs = [posts[x["seq"]] for x in ed["slots"] if x["slot"] == "brief" and x["seq"] in posts]
    if briefs:
        head("단신")
        for p in briefs:
            h.append(f'<p style="font-size:15px;line-height:1.6;margin:0 0 10px"><a href="{base}/p/{p["seq"]}" '
                     f'style="color:#1d1a16;font-weight:600">{E(p["title"])}</a> {E(p["summary"])}</p>')
            t.append(f"· {p['title']} — {p['summary']} {base}/p/{p['seq']}")
    for slot, label in (("background", "오늘의 배경"), ("culture", "교양")):
        items = [posts[x["seq"]] for x in ed["slots"] if x["slot"] == slot and x["seq"] in posts]
        if items:
            head(label)
            for p in items:
                article(p, full=(slot == "culture"))

    how = f"{base}/front/{ed['edition_date']}"
    h.append(f'<p style="font-size:12px;color:#8a8175;border-top:1px solid #d9cfbd;padding-top:14px;margin-top:32px">'
             f'모든 글은 AI가 여러 언론 보도를 종합해 썼습니다. <a href="{how}" style="color:#8a8175">1면은 이렇게 골랐습니다</a> · '
             f'<a href="{base}/principles" style="color:#8a8175">편집 원칙</a> · '
             f'<a href="{base}/settings" style="color:#8a8175">설정</a> · '
             f'<a href="{unsub}" style="color:#8a8175">수신 거부</a></p></div>')
    t.append(f"\n1면은 이렇게 골랐습니다: {how}\n편집 원칙: {base}/principles\n수신 거부: {unsub}")
    front_titles = [posts[x["seq"]]["title"] for x in ed["slots"] if x["slot"] == "front" and x["seq"] in posts]
    subject = f"[오늘판 {date_str}] " + (front_titles[0] if front_titles else "오늘의 조간")
    return RenderedEmail(subject=subject, html="".join(h), text="\n".join(t), unsubscribe_url=unsub)
