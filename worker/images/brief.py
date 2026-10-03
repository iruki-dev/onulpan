"""글 한 편의 이미지 검색 정보(분야, 대상 종류, 검색어, 대체 텍스트).

Claude를 쓸 수 있으면 짧은 호출 한 번으로 만들고, 없으면 낱말 규칙으로 만든다.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass

import psycopg

from ..generate.gateway import LLMClient, record_call
from ..generate.prompts import load_prompt, parse_json_output
from ..nlp import proper_nouns
from ..settings import Settings
from .policy import registry

log = logging.getLogger(__name__)

FIELDS = ("space", "health", "climate", "tech", "science", "politics", "economy", "culture", "world", "society")
SUBJECTS = ("person", "place", "object", "event", "concept", "data")


@dataclass
class Brief:
    field: str
    subject: str
    query_ko: str
    query_en: str | None
    alt: str
    by: str = "rules"

    def to_json(self) -> dict:
        return asdict(self)


def classify_field(section: str, text: str) -> str:
    reg = registry()
    target = reg["section_fields"].get(section, "society")
    kw = reg["field_keywords"]
    if isinstance(target, list):
        for f in target:
            if any(k in text for k in kw.get(f, [])):
                return f
        return "science"
    return target


def rule_brief(post: dict, display_name: str | None = None) -> Brief:
    text = f"{post['title']} {post.get('summary') or ''}"
    field = classify_field(post["section"], text)
    nouns = proper_nouns(post["title"])
    query_ko = display_name or (" ".join(nouns[:2]) if nouns else post["title"][:20])
    subject = "concept" if not nouns else "event"
    return Brief(field=field, subject=subject, query_ko=query_ko, query_en=None,
                 alt=f"{query_ko} 관련 이미지"[:40], by="rules")


def llm_brief(conn: psycopg.Connection, llm: LLMClient, s: Settings, post: dict) -> Brief | None:
    user = f"<post>\n제목: {post['title']}\n요약: {post.get('summary') or ''}\n분야: {post['section']}\n" \
           f"본문 앞부분: {(post.get('body_md') or '')[:500]}\n</post>"
    params = {"model": s["images"]["brief_model"], "max_tokens": 300, "system": load_prompt("image.v1"),
              "messages": [{"role": "user", "content": user}]}
    try:
        res = llm.create(params)
    except RuntimeError as e:
        log.warning("image brief failed: %s", e)
        return None
    record_call(conn, "image_brief", res)
    if not res.ok:
        return None
    try:
        d = parse_json_output(res.text)
    except (ValueError, json.JSONDecodeError):
        return None
    field = d.get("field") if d.get("field") in FIELDS else classify_field(post["section"], post["title"])
    subject = d.get("subject") if d.get("subject") in SUBJECTS else "concept"
    alt = str(d.get("alt") or post["title"])[:60]
    return Brief(field=field, subject=subject, query_ko=str(d.get("query_ko") or post["title"][:20]),
                 query_en=(str(d["query_en"]).strip() or None) if d.get("query_en") else None, alt=alt, by="llm")


def make_brief(conn: psycopg.Connection, s: Settings, post: dict, llm: LLMClient | None) -> Brief:
    display = None
    if post.get("slug"):
        row = conn.execute("SELECT display_name FROM slugs WHERE slug = %s", (post["slug"],)).fetchone()
        display = row["display_name"] if row else None
    if llm is not None and s["images"].get("brief_llm"):
        b = llm_brief(conn, llm, s, post)
        if b:
            return b
    return rule_brief(post, display)
