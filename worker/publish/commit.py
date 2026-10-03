"""7단계 게시: posts, post_sources, post_links, term_mentions를 한 트랜잭션으로 쓴다.

글은 추가만 된다. 정정·후속·갱신은 모두 새 글이다.
"""
from __future__ import annotations

import re
from datetime import datetime

import psycopg

from ..db import jsonb, log_decision, vec
from ..generate.schema import render_issue_body
from ..nlp import char_count, normalize_ws
from ..process.embed import Embedder
from ..process.importance import importance
from ..settings import Settings
from . import links


def _doc_ids(ids: list[str], prefix: str) -> list[int]:
    return [int(i[len(prefix):]) for i in ids if i.startswith(prefix) and i[len(prefix):].isdigit()]


def _cited(draft: dict) -> list[str]:
    ids: list[str] = []
    for f in draft.get("facts") or []:
        ids.extend(f.get("source_ids") or [])
    for p in (draft.get("sections") or {}).get("positions") or []:
        ids.extend(p.get("source_ids") or [])
    return list(dict.fromkeys(ids))


def _post_importance(conn: psycopg.Connection, req: dict, kind: str, now: datetime, s: Settings) -> float:
    imp = s["importance"]
    if kind in ("fact", "issue") and req.get("cluster_id"):
        c = conn.execute("SELECT * FROM clusters WHERE id = %s", (req["cluster_id"],)).fetchone()
        return importance(c["n_outlets"], c["n_groups"], c["last_seen"], now, imp["group_bonus"], imp["decay_hours"])
    if kind == "synthesis":
        seqs = _doc_ids([d["id"] for d in (req.get("input") or {}).get("docs", [])], "p_")
        if seqs:
            row = conn.execute("SELECT max(importance) AS m FROM posts WHERE seq = ANY(%s)", (seqs,)).fetchone()
            return float(row["m"] or 0)
    return 0.0


def _raw_sources(conn: psycopg.Connection, raw_ids: list[int]) -> list[dict]:
    if not raw_ids:
        return []
    return conn.execute(
        "SELECT id, outlet_id, url, title FROM raw_articles WHERE id = ANY(%s) ORDER BY id", (raw_ids,)
    ).fetchall()


def publish(conn: psycopg.Connection, s: Settings, embedder: Embedder, req: dict, draft: dict,
            verify_report: dict, now: datetime, review: str | None = None) -> int:
    """생성 요청 하나의 검증된 초안을 게시하고 seq를 돌려준다. 호출자가 트랜잭션을 연다."""
    kind = str(req["kind"])
    docs = {d["id"]: d for d in (req.get("input") or {}).get("docs", [])}
    cluster = None
    if req.get("cluster_id"):
        cluster = conn.execute("SELECT * FROM clusters WHERE id = %s", (req["cluster_id"],)).fetchone()

    # slug: 묶음에 이미 붙은 slug > 요청 slug(종합) > 모델 제안
    extra = [req["term"]] if req.get("term") else []
    if cluster and cluster["slug"]:
        slug = cluster["slug"]
    elif kind == "synthesis" and req.get("slug"):
        slug = req["slug"]
    elif kind == "explainer" and req.get("term"):
        slug = links.resolve_slug(conn, req["term"], extra)
    else:
        slug = links.resolve_slug(conn, draft.get("slug_suggestion") or draft["title"], extra)

    body = render_issue_body(draft.get("sections") or {}) if kind == "issue" else draft["body_md"].strip()
    section = "culture" if kind == "culture" else draft.get("section", "none")
    meta = {
        "facts": draft.get("facts") or [],
        "quotes": draft.get("quotes") or [],
        "terms": draft.get("terms") or [],
        "disputed": bool(draft.get("disputed")),
        "conflicts": draft.get("conflicts") or [],
        "request_id": req["id"],
        "attempt": req["attempt"],
        "review": review,
    }
    if kind == "issue":
        meta["sections"] = draft.get("sections")
    if kind == "culture":
        meta["calendar_date"] = (req.get("topic") or {}).get("date")
        meta["area"] = (req.get("topic") or {}).get("area")
    if cluster:
        meta["cluster"] = {"n_outlets": cluster["n_outlets"], "n_groups": cluster["n_groups"],
                           "last_seen": cluster["last_seen"].isoformat()}

    cost = conn.execute(
        """WITH RECURSIVE chain AS (
             SELECT id, parent_id, cost_usd FROM generation_requests WHERE id = %s
             UNION ALL SELECT g.id, g.parent_id, g.cost_usd FROM generation_requests g JOIN chain c ON g.id = c.parent_id)
           SELECT COALESCE(sum(cost_usd), 0) AS c FROM chain""",
        (req["id"],),
    ).fetchone()["c"]
    emb = embedder.embed([f"{draft['title']}\n{draft['summary']}\n{body[:600]}"])[0]

    seq = conn.execute(
        """INSERT INTO posts (kind, section, slug, cluster_id, title, summary, body_md, char_count, meta, importance,
                              model, prompt_version, verify_report, cost_usd, embedding, created_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::vector,%s) RETURNING seq""",
        (kind, section, slug, req.get("cluster_id"), normalize_ws(draft["title"]), normalize_ws(draft["summary"]),
         body, char_count(body), jsonb(meta), _post_importance(conn, req, kind, now, s),
         req.get("model") or s["generate"]["model"], req.get("prompt_version") or "unknown",
         jsonb(verify_report), cost, vec(emb), now),
    ).fetchone()["seq"]

    # 출처: 인용한 문서(없으면 입력 전체)의 원문 기사
    cited = [c for c in _cited(draft) if c in docs] or list(docs)
    raw_ids: list[int] = []
    for c in cited:
        raw_ids.extend(docs[c].get("raw_ids") or [])
    for r in _raw_sources(conn, sorted(set(raw_ids))):
        conn.execute(
            """INSERT INTO post_sources (post_seq, raw_article_id, outlet_id, url, title)
               VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
            (seq, r["id"], r["outlet_id"], r["url"], r["title"]),
        )

    # 링크: 같은 slug의 이전 글(follows), 종합·해설의 입력 글(summarizes/refers), 본문 용어 사전 매칭
    prev = conn.execute(
        "SELECT seq FROM posts WHERE slug = %s AND seq < %s ORDER BY seq DESC LIMIT 1", (slug, seq)
    ).fetchone()
    if prev and kind in ("fact", "synthesis", "issue", "explainer"):
        links.insert_link(conn, seq, prev["seq"], "follows")
    if kind in ("synthesis", "explainer"):
        rel = "summarizes" if kind == "synthesis" else "refers"
        for p in _doc_ids(list(docs), "p_"):
            links.insert_link(conn, seq, p, rel)
    built = links.build_links(conn, seq, slug, body)

    # 해설 후보 용어
    for t in draft.get("terms") or []:
        t = normalize_ws(str(t))
        if 2 <= len(t) <= 30:
            conn.execute("INSERT INTO term_mentions (term, post_seq) VALUES (%s, %s) ON CONFLICT DO NOTHING", (t, seq))

    if cluster:
        conn.execute("UPDATE clusters SET state = 'written', written_at = %s, slug = COALESCE(slug, %s) WHERE id = %s",
                     (now, slug, cluster["id"]))
    log_decision(conn, "publish", f"post:{seq}", {"request_id": req["id"], "kind": kind, "slug": slug,
                                                  "links": built, "review": review})
    return seq


def publish_correction(conn: psycopg.Connection, embedder: Embedder, *, target_seq: int, title: str, body: str,
                       summary: str, author: str, now: datetime) -> int:
    """정정 글: 무엇이 틀렸고 무엇이 맞는지. 원래 글 위에는 웹이 역참조(corrects)로 띠를 붙인다."""
    orig = conn.execute("SELECT * FROM posts WHERE seq = %s", (target_seq,)).fetchone()
    if orig is None:
        raise ValueError(f"post {target_seq} not found")
    title = normalize_ws(title)[:36] or f"정정: {orig['title']}"[:36]
    summary = normalize_ws(summary)[:80]
    body = re.sub(r"\n{3,}", "\n\n", body.strip())
    emb = embedder.embed([f"{title}\n{summary}\n{body[:600]}"])[0]
    seq = conn.execute(
        """INSERT INTO posts (kind, section, slug, cluster_id, title, summary, body_md, char_count, meta, importance,
                              model, prompt_version, verify_report, cost_usd, embedding, created_at)
           VALUES ('correction',%s,%s,%s,%s,%s,%s,%s,%s,%s,'human','manual',%s,0,%s::vector,%s) RETURNING seq""",
        (orig["section"], orig["slug"], orig["cluster_id"], title, summary, body, char_count(body),
         jsonb({"corrects": target_seq, "author": author}), orig["importance"],
         jsonb({"passed": True, "action": "pass", "manual": True, "by": author}), vec(emb), now),
    ).fetchone()["seq"]
    conn.execute(
        """INSERT INTO post_sources (post_seq, raw_article_id, outlet_id, url, title)
           SELECT %s, raw_article_id, outlet_id, url, title FROM post_sources WHERE post_seq = %s""",
        (seq, target_seq),
    )
    links.insert_link(conn, seq, target_seq, "corrects", None)
    log_decision(conn, "publish", f"post:{seq}", {"kind": "correction", "corrects": target_seq, "author": author})
    return seq
