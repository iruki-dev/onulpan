"""1면 선정 (매일 06:25, 사람 검토 직후). 1면은 모든 사용자에게 같다.

직전 24시간 사실·종합 글 중 importance 상위에서 서로 다른 slug 3편(같은 섹션 최대 2편).
후보 상위 10편의 점수와 탈락 사유를 decision_log(kind='select')에 남기고, 조간 하단 ‘1면은 이렇게 골랐습니다’에서 공개한다.
후보가 3편 미만이면 전날 1면의 종합 글로 채우고 표시한다.
클릭 수, 체류 시간, 공유 수는 쓰지 않는다.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import psycopg

from ..db import log_decision
from ..process.importance import explain
from ..settings import Settings


def _candidates(conn: psycopg.Connection, now: datetime, s: Settings) -> list[dict]:
    f = s["front"]
    imp = s["importance"]
    rows = conn.execute(
        """SELECT p.seq, p.kind::text AS kind, p.section::text AS section, p.slug, p.title, p.importance,
                  c.n_outlets, c.n_groups, c.last_seen
           FROM posts p LEFT JOIN clusters c ON c.id = p.cluster_id
           WHERE p.kind IN ('fact','synthesis') AND p.created_at > %s AND p.created_at <= %s
             AND NOT EXISTS (SELECT 1 FROM post_links l JOIN posts x ON x.seq = l.from_seq
                             WHERE l.to_seq = p.seq AND l.rel = 'corrects')""",
        (now - timedelta(hours=f["window_hours"]), now),
    ).fetchall()
    for r in rows:
        if r["last_seen"] is not None:
            r["explain"] = explain(r["n_outlets"], r["n_groups"], r["last_seen"], now, imp["group_bonus"], imp["decay_hours"])
            r["score"] = r["explain"]["score"]
        else:
            r["explain"] = {"stored_importance": round(float(r["importance"]), 4)}
            r["score"] = round(float(r["importance"]), 4)
    rows.sort(key=lambda r: (-r["score"], r["seq"]))
    return rows


def select_front(conn: psycopg.Connection, d: date, now: datetime, s: Settings) -> dict:
    f = s["front"]
    cands = _candidates(conn, now, s)
    picked: list[dict] = []
    per_section: dict[str, int] = {}
    slugs: set[str] = set()
    log_rows = []
    for rank, r in enumerate(cands):
        reason = None
        if len(picked) >= f["n"]:
            reason = "1면 3편이 이미 찼음"
        elif r["slug"] and r["slug"] in slugs:
            reason = "같은 주제가 이미 1면에 있음"
        elif per_section.get(r["section"], 0) >= f["same_section_max"]:
            reason = f"같은 분야는 최대 {f['same_section_max']}편"
        if reason is None:
            picked.append(r)
            slugs.add(r["slug"])
            per_section[r["section"]] = per_section.get(r["section"], 0) + 1
        if rank < f["log_top"]:
            log_rows.append({"rank": rank + 1, "seq": r["seq"], "title": r["title"], "section": r["section"],
                             "slug": r["slug"], "kind": r["kind"], "score": r["score"], "explain": r["explain"],
                             "picked": reason is None, "reason": reason})

    fallback = False
    if len(picked) < f["n"]:
        prev = conn.execute(
            "SELECT seqs FROM front_pages WHERE edition_date < %s ORDER BY edition_date DESC, id DESC LIMIT 1", (d,)
        ).fetchone()
        if prev:
            for row in conn.execute(
                """SELECT DISTINCT ON (p.slug) s2.seq, s2.slug, s2.section::text AS section, s2.title
                   FROM posts p JOIN LATERAL (
                     SELECT seq, slug, section, title FROM posts
                     WHERE slug = p.slug AND kind = 'synthesis' AND created_at <= %s ORDER BY seq DESC LIMIT 1) s2 ON true
                   WHERE p.seq = ANY(%s)
                   ORDER BY p.slug, s2.seq""",
                (now, prev["seqs"]),
            ).fetchall():
                if len(picked) >= f["n"]:
                    break
                if row["slug"] in slugs:
                    continue
                picked.append(row)
                slugs.add(row["slug"])
                fallback = True

    issue = conn.execute(
        """SELECT seq FROM posts WHERE kind = 'issue' AND created_at > %s AND created_at <= %s
           ORDER BY importance DESC, seq LIMIT 1""",
        (now - timedelta(hours=24), now),
    ).fetchone()
    seqs = [r["seq"] for r in picked]
    row = conn.execute(
        "INSERT INTO front_pages (edition_date, seqs, fallback, issue_seq) VALUES (%s, %s, %s, %s) RETURNING *",
        (d, seqs, fallback, issue["seq"] if issue else None),
    ).fetchone()
    log_decision(conn, "select", f"front:{d}", {
        "edition_date": str(d), "at": now.isoformat(), "picked": seqs, "fallback": fallback,
        "issue_seq": row["issue_seq"], "n_candidates": len(cands), "top": log_rows,
        "formula": "log2(1+언론사 수) × (1+0.25×(언론사 형태 수−1)) × e^(−경과시간/18h)",
    })
    return row


def get_front(conn: psycopg.Connection, d: date) -> dict | None:
    return conn.execute(
        "SELECT * FROM front_pages WHERE edition_date = %s ORDER BY id DESC LIMIT 1", (d,)
    ).fetchone()


def get_or_select_front(conn: psycopg.Connection, d: date, now: datetime, s: Settings) -> dict:
    """06:25 이전에 조립 요청이 오면 그 자리에서 한 번 계산해 저장한다. 이후 모든 사용자가 같은 1면을 쓴다."""
    row = get_front(conn, d)
    if row:
        return row
    conn.execute("SELECT pg_advisory_xact_lock(hashtext('front:' || %s))", (str(d),))
    return get_front(conn, d) or select_front(conn, d, now, s)
