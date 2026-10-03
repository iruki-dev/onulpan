"""7단계 링크: 본문 용어를 slug_aliases와 사전 매칭해 만든다.

LLM이 링크를 만들지 않으므로 깨진 링크가 없다. post_links는 항상 특정 글(to_seq)을 가리키고,
화면은 to_seq의 slug로 최신 글을 찾아 보여주며 ‘이 글이 쓰일 당시의 버전’ 링크를 함께 둔다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import psycopg

from ..nlp import normalize_ws

SLUG_BAD = re.compile(r"[^0-9A-Za-z가-힣\-]")


def normalize_slug(s: str) -> str:
    s = normalize_ws(s).replace(" ", "-").replace("_", "-")
    s = SLUG_BAD.sub("", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s[:60]


def display_of(slug: str) -> str:
    return slug.replace("-", " ")


def add_alias(conn: psycopg.Connection, alias: str, slug: str) -> None:
    alias = normalize_ws(alias)
    if len(alias) >= 2:
        conn.execute("INSERT INTO slug_aliases (alias, slug) VALUES (%s, %s) ON CONFLICT (alias) DO NOTHING", (alias, slug))


def resolve_slug(conn: psycopg.Connection, suggestion: str, extra_aliases: list[str] | None = None) -> str:
    """제안된 slug가 기존 slug·별칭과 맞으면 그것을, 아니면 새로 만든다."""
    raw = normalize_ws(suggestion or "")
    slug = normalize_slug(raw) or "기타"
    if conn.execute("SELECT 1 FROM slugs WHERE slug = %s", (slug,)).fetchone():
        return slug
    for cand in (raw, display_of(slug), slug.replace("-", "")):
        row = conn.execute("SELECT slug FROM slug_aliases WHERE alias = %s", (cand,)).fetchone()
        if row:
            return row["slug"]
    conn.execute("INSERT INTO slugs (slug, display_name) VALUES (%s, %s)", (slug, display_of(slug)))
    add_alias(conn, display_of(slug), slug)
    add_alias(conn, slug.replace("-", ""), slug)
    for a in extra_aliases or []:
        add_alias(conn, a, slug)
    return slug


@dataclass
class Match:
    slug: str
    anchor: str
    start: int


def dictionary(conn: psycopg.Connection) -> list[tuple[str, str]]:
    rows = conn.execute(
        """SELECT alias AS term, slug FROM slug_aliases
           UNION SELECT display_name, slug FROM slugs"""
    ).fetchall()
    terms = [(r["term"], r["slug"]) for r in rows if len(r["term"]) >= 2]
    terms.sort(key=lambda x: (-len(x[0]), x[0]))  # 긴 표기 먼저 (결정적 순서)
    return terms


def match_terms(text: str, terms: list[tuple[str, str]]) -> list[Match]:
    """겹치지 않게, 긴 표기 우선. 앞이 한글·영문에 붙어 있으면 다른 낱말의 일부로 본다 (뒤의 조사는 허용)."""
    taken = [False] * len(text)
    found: dict[str, Match] = {}
    for term, slug in terms:
        if slug in found:
            continue
        for m in re.finditer(re.escape(term), text):
            a, b = m.span()
            if a > 0 and re.match(r"[가-힣A-Za-z0-9]", text[a - 1]):
                continue
            if any(taken[a:b]):
                continue
            for i in range(a, b):
                taken[i] = True
            found[slug] = Match(slug, term, a)
            break
    return sorted(found.values(), key=lambda m: m.start)


def link_target(conn: psycopg.Connection, slug: str, before_seq: int) -> tuple[int, str] | None:
    row = conn.execute(
        """SELECT seq, kind::text AS kind FROM posts
           WHERE slug = %s AND seq < %s AND kind IN ('explainer','synthesis','fact','issue')
           ORDER BY (kind = 'explainer') DESC, (kind = 'synthesis') DESC, seq DESC LIMIT 1""",
        (slug, before_seq),
    ).fetchone()
    if not row:
        return None
    return row["seq"], ("explains" if row["kind"] == "explainer" else "refers")


def insert_link(conn: psycopg.Connection, from_seq: int, to_seq: int, rel: str, anchor: str | None = None) -> None:
    if to_seq >= from_seq:
        return
    conn.execute(
        """INSERT INTO post_links (from_seq, to_seq, rel, anchor_text) VALUES (%s, %s, %s, %s)
           ON CONFLICT DO NOTHING""",
        (from_seq, to_seq, rel, anchor),
    )


def build_links(conn: psycopg.Connection, seq: int, own_slug: str | None, text: str) -> list[dict]:
    out = []
    for m in match_terms(text, dictionary(conn)):
        if m.slug == own_slug:
            continue
        t = link_target(conn, m.slug, seq)
        if t:
            insert_link(conn, seq, t[0], t[1], m.anchor)
            out.append({"to": t[0], "rel": t[1], "anchor": m.anchor})
    return out
