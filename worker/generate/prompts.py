"""5단계 프롬프트 조립.

공통 시스템 프롬프트 1개 + 글 종류별 지시문. 공통 시스템 프롬프트는 모든 요청에서 같으므로 프롬프트 캐시에 올린다.
프롬프트는 prompts/ 디렉터리에 버전 번호와 함께 두고, 글마다 prompt_version을 기록한다.

입력 문서 id: 원문 기사는 r_<raw_articles.id>, 우리 글은 p_<posts.seq>.
검증이 같은 텍스트로 대조할 수 있도록 모델이 본 문서 텍스트를 요청 input에 함께 저장한다.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache

import psycopg

from ..settings import PROMPTS_DIR, RULES_DIR, Settings

SYSTEM_VERSION = "system.v1"
KIND_VERSION = {
    "fact": "fact.v1", "synthesis": "synthesis.v1", "issue": "issue.v1",
    "explainer": "explainer.v1", "culture": "culture.v1",
}
RETRY_VERSION = "retry.v1"


@lru_cache(maxsize=None)
def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def glossary_pairs() -> list[tuple[str, str]]:
    pairs = []
    for line in (RULES_DIR / "glossary.tsv").read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        cols = line.split("\t")
        if len(cols) >= 2:
            pairs.append((cols[0].strip(), cols[1].strip()))
    return pairs


def system_prompt() -> str:
    pairs = glossary_pairs()
    block = ""
    if pairs:
        block = "\n[용어 규칙]\n" + "\n".join(f"{a} 대신 {b}" for a, b in pairs)
    return load_prompt(SYSTEM_VERSION).replace("{glossary_block}", block).strip()


def prompt_version(kind: str) -> str:
    return f"{SYSTEM_VERSION}+{KIND_VERSION[kind]}"


@dataclass
class Doc:
    id: str                     # r_123 | p_45
    text: str                   # 모델에게 보여준 텍스트 (제목 포함)
    outlet_ids: list[int]       # 이 문서가 기대는 매체들 (V2)
    raw_ids: list[int]          # post_sources로 남길 원문 기사들
    title: str = ""
    outlet: str = ""
    group: str = ""
    published: str = ""
    kind: str = "raw"

    def to_json(self) -> dict:
        return self.__dict__.copy()


# ── 입력 문서 고르기 ───────────────────────────────────

def pick_articles(conn: psycopg.Connection, cluster_id: int, s: Settings) -> list[Doc]:
    """매체군이 겹치지 않게 최대 6건 추출, 건당 본문 1,500자로 자름."""
    g = s["generate"]
    rows = conn.execute(
        """SELECT r.id, r.title, r.body, r.published_at, r.outlet_id, o.name AS outlet, o.grp::text AS grp
           FROM raw_articles r JOIN outlets o ON o.id = r.outlet_id
           WHERE r.cluster_id = %s AND r.duplicate_of IS NULL AND r.body IS NOT NULL
           ORDER BY r.published_at, r.id""",
        (cluster_id,),
    ).fetchall()
    chosen: list[dict] = []
    used_groups: set[str] = set()
    used_outlets: set[int] = set()
    # 1차: 매체군마다 하나씩, 2차: 남은 매체마다 하나씩, 3차: 나머지
    for pass_ in (1, 2, 3):
        for r in rows:
            if len(chosen) >= g["max_articles"] or r in chosen:
                continue
            if pass_ == 1 and (r["grp"] in used_groups or r["outlet_id"] in used_outlets):
                continue
            if pass_ == 2 and r["outlet_id"] in used_outlets:
                continue
            chosen.append(r)
            used_groups.add(r["grp"])
            used_outlets.add(r["outlet_id"])
    chosen.sort(key=lambda r: (r["published_at"], r["id"]))
    return [
        Doc(id=f"r_{r['id']}", title=r["title"], text=f"제목: {r['title']}\n본문: {r['body'][: g['article_chars']]}",
            outlet_ids=[r["outlet_id"]], raw_ids=[r["id"]], outlet=r["outlet"], group=r["grp"],
            published=r["published_at"].isoformat(timespec="minutes"), kind="raw")
        for r in chosen
    ]


def post_doc(conn: psycopg.Connection, row: dict) -> Doc:
    src = conn.execute(
        "SELECT raw_article_id, outlet_id FROM post_sources WHERE post_seq = %s ORDER BY raw_article_id", (row["seq"],)
    ).fetchall()
    return Doc(
        id=f"p_{row['seq']}", title=row["title"], kind=str(row["kind"]),
        text=f"제목: {row['title']}\n요약: {row['summary']}\n본문: {row['body_md']}",
        outlet_ids=sorted({r["outlet_id"] for r in src}), raw_ids=[r["raw_article_id"] for r in src],
        published=row["created_at"].isoformat(timespec="minutes"),
    )


def related_posts(conn: psycopg.Connection, cluster_id: int | None, slug: str | None, n: int) -> list[dict]:
    if slug:
        rows = conn.execute(
            """SELECT seq, slug, kind::text AS kind, title, summary FROM posts
               WHERE slug = %s AND kind IN ('fact','synthesis') ORDER BY seq DESC LIMIT %s""",
            (slug, n),
        ).fetchall()
        if rows:
            return rows
    if cluster_id is None:
        return []
    return conn.execute(
        """SELECT p.seq, p.slug, p.kind::text AS kind, p.title, p.summary
           FROM posts p, clusters c
           WHERE c.id = %s AND p.embedding IS NOT NULL AND p.kind IN ('fact','synthesis')
             AND p.created_at > now() - interval '30 days'
             AND 1 - (p.embedding <=> c.centroid) >= 0.6
           ORDER BY p.embedding <=> c.centroid LIMIT %s""",
        (cluster_id, n),
    ).fetchall()


def known_terms(conn: psycopg.Connection, limit: int = 200) -> list[str]:
    rows = conn.execute(
        """SELECT DISTINCT s.display_name FROM slugs s
           WHERE EXISTS (SELECT 1 FROM posts p WHERE p.slug = s.slug AND p.kind = 'explainer')
           ORDER BY 1 LIMIT %s""",
        (limit,),
    ).fetchall()
    return [r["display_name"] for r in rows]


def existing_slugs(conn: psycopg.Connection, cluster_id: int | None, limit: int = 30) -> list[str]:
    """모델이 기존 slug를 고를 수 있도록 가까운 slug 목록을 준다."""
    if cluster_id is None:
        return []
    rows = conn.execute(
        """SELECT DISTINCT ON (p.slug) p.slug, p.embedding <=> c.centroid AS d
           FROM posts p, clusters c
           WHERE c.id = %s AND p.slug IS NOT NULL AND p.embedding IS NOT NULL
           ORDER BY p.slug, d""",
        (cluster_id,),
    ).fetchall()
    rows.sort(key=lambda r: r["d"])
    return [r["slug"] for r in rows[:limit]]


# ── 사용자 메시지 렌더링 ────────────────────────────────

def _articles_xml(docs: list[Doc]) -> str:
    parts = ["<articles>"]
    for d in docs:
        parts.append(f'<article id="{d.id}" outlet="{d.outlet}" group="{d.group}" published="{d.published}">')
        parts.append(d.text)
        parts.append("</article>")
    parts.append("</articles>")
    return "\n".join(parts)


def _posts_xml(tag: str, docs: list[Doc]) -> str:
    parts = [f"<{tag}>"]
    for d in docs:
        parts.append(f'<post id="{d.id}" kind="{d.kind}" published="{d.published}">')
        parts.append(d.text)
        parts.append("</post>")
    parts.append(f"</{tag}>")
    return "\n".join(parts)


def render_user(kind: str, docs: list[Doc], related: list[dict], terms: list[str], slugs: list[str],
                spec: dict) -> str:
    instr = load_prompt(KIND_VERSION[kind])
    for k, v in spec.items():
        instr = instr.replace("{" + k + "}", str(v))
    out = [instr, ""]
    if kind in ("fact", "issue"):
        out.append(_articles_xml(docs))
    elif kind in ("synthesis", "explainer"):
        out.append(_posts_xml("posts", docs))
    if kind in ("fact", "issue", "synthesis"):
        out.append("<related_posts>")
        for r in related:
            out.append(f'<post seq="{r["seq"]}" slug="{r["slug"] or ""}" kind="{r["kind"]}">{r["title"]} / {r["summary"]}</post>')
        out.append("</related_posts>")
        if slugs:
            out.append("<existing_slugs>\n" + ", ".join(slugs) + "\n</existing_slugs>")
    if kind != "culture":
        out.append("<known_terms>\n" + ", ".join(terms) + "\n</known_terms>")
    return "\n".join(out)


def build_params(kind: str, user_text: str, s: Settings, retry: dict | None = None) -> dict:
    g = s["generate"]
    messages: list[dict] = [{"role": "user", "content": user_text}]
    if retry:
        failures = "\n".join(f"- {f['rule']}: {f['message']}" for f in retry["failures"])
        messages.append({"role": "assistant", "content": retry["previous"] or "{}"})
        messages.append({"role": "user", "content": load_prompt(RETRY_VERSION).replace("{failures}", failures)})
    params: dict = {
        "model": g["model"],
        "max_tokens": int(g["max_tokens"][kind]),
        "system": [{"type": "text", "text": system_prompt(), "cache_control": {"type": "ephemeral"}}],
        "messages": messages,
    }
    if g.get("thinking") == "disabled":
        params["thinking"] = {"type": "disabled"}
    if g.get("structured_output"):
        from .schema import json_schema_for

        params["output_config"] = {"format": {"type": "json_schema", "schema": json_schema_for(kind)}}
    return params


def parse_json_output(text: str) -> dict:
    """JSON 하나만 받는다. 코드 울타리가 붙어 오면 걷어 낸다. 실패는 V1 실패로 취급된다."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else ""
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    start, end = t.find("{"), t.rfind("}")
    if start < 0 or end < start:
        raise ValueError("JSON 객체를 찾지 못함")
    return json.loads(t[start : end + 1])
