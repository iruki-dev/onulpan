"""6~8단계 이음: 받은 초안 검증 → (베타) drafts 또는 (출시) posts → 후속 트리거. 재생성은 1회뿐이다."""
from __future__ import annotations

import logging
from datetime import datetime

import psycopg

from .db import jsonb, log_decision
from .generate.gateway import LLMClient
from .process.embed import Embedder
from .publish import commit, triggers
from .settings import Settings
from .verify.base import Context
from .verify.runner import failures_for_retry, make_semantic_judge, run_rules

log = logging.getLogger(__name__)


def allowed_names(conn: psycopg.Connection) -> set[str]:
    rows = conn.execute(
        """SELECT display_name AS n FROM slugs UNION SELECT alias FROM slug_aliases UNION SELECT name FROM outlets"""
    ).fetchall()
    return {r["n"] for r in rows}


def build_context(conn: psycopg.Connection, req: dict, s: Settings, embedder: Embedder,
                  llm: LLMClient | None) -> Context:
    resp = req.get("response") or {}
    docs = {d["id"]: d for d in (req.get("input") or {}).get("docs", [])}
    return Context(
        kind=str(req["kind"]),
        draft=resp.get("parsed"),
        raw_text=resp.get("raw") or "",
        parse_error=resp.get("parse_error") or resp.get("error"),
        docs=docs,
        s=s,
        names=allowed_names(conn),
        embed=embedder.embed,
        embedder_name=embedder.name,
        semantic_judge=make_semantic_judge(conn, llm, s) if (llm is not None and s["verify"].get("semantic_llm")) else None,
    )


def _close_cluster_skipped(conn: psycopg.Connection, req: dict, report: dict, reason: str) -> None:
    if req.get("cluster_id") and str(req["kind"]) == "fact":
        conn.execute("UPDATE clusters SET state = 'skipped' WHERE id = %s AND state = 'open'", (req["cluster_id"],))
    failed = [r["id"] for r in report["rules"] if not r["ok"]]
    log_decision(conn, "verify", f"request:{req['id']}", {
        "outcome": "skipped", "reason": reason, "kind": str(req["kind"]), "cluster_id": req.get("cluster_id"),
        "attempt": req["attempt"], "failed_rules": failed,
    })


def process_received(conn: psycopg.Connection, s: Settings, embedder: Embedder, llm: LLMClient | None,
                     now: datetime) -> dict:
    stats = {"passed": 0, "retry": 0, "failed": 0, "discarded": 0, "published": 0, "drafted": 0}
    reqs = conn.execute("SELECT * FROM generation_requests WHERE status = 'received' ORDER BY id").fetchall()
    for req in reqs:
        ctx = build_context(conn, req, s, embedder, llm)
        report = run_rules(ctx)
        with conn.transaction():
            conn.execute("UPDATE generation_requests SET verify_report = %s, finished_at = %s WHERE id = %s",
                         (jsonb(report), now, req["id"]))
            if report["action"] == "pass":
                stats["passed"] += 1
                log_decision(conn, "verify", f"request:{req['id']}", {"outcome": "passed", "kind": str(req["kind"]),
                                                                      "attempt": req["attempt"]})
                if s["review"]["enabled"]:
                    conn.execute(
                        """INSERT INTO drafts (cluster_id, request_id, kind, payload, verify_report)
                           VALUES (%s, %s, %s, %s, %s)""",
                        (req.get("cluster_id"), req["id"], req["kind"], jsonb(ctx.draft), jsonb(report)),
                    )
                    conn.execute("UPDATE generation_requests SET status = 'drafted' WHERE id = %s", (req["id"],))
                    stats["drafted"] += 1
                else:
                    seq = commit.publish(conn, s, embedder, req, ctx.draft, report, now)
                    conn.execute("UPDATE generation_requests SET status = 'published' WHERE id = %s", (req["id"],))
                    triggers.after_publish(conn, seq, now, s)
                    stats["published"] += 1
            elif report["action"] == "discard":
                conn.execute("UPDATE generation_requests SET status = 'discarded' WHERE id = %s", (req["id"],))
                _close_cluster_skipped(conn, req, report, "V2: 출처 부족")
                stats["discarded"] += 1
            elif req["attempt"] == 1:
                conn.execute("UPDATE generation_requests SET status = 'retry' WHERE id = %s", (req["id"],))
                feedback = {"failures": failures_for_retry(report), "previous": ctx.raw_text[:6000]}
                conn.execute(
                    """INSERT INTO generation_requests (kind, cluster_id, slug, term, topic, attempt, parent_id,
                                                        priority, mode, feedback, created_at)
                       VALUES (%s,%s,%s,%s,%s,2,%s,%s,%s,%s,%s)""",
                    (req["kind"], req.get("cluster_id"), req.get("slug"), req.get("term"),
                     jsonb(req["topic"]) if req.get("topic") else None, req["id"], req["priority"], req["mode"],
                     jsonb(feedback), now),
                )
                log_decision(conn, "verify", f"request:{req['id']}", {
                    "outcome": "retry", "kind": str(req["kind"]),
                    "failed_rules": [r["id"] for r in report["rules"] if not r["ok"]]})
                stats["retry"] += 1
            else:
                conn.execute("UPDATE generation_requests SET status = 'failed' WHERE id = %s", (req["id"],))
                _close_cluster_skipped(conn, req, report, "재생성 후에도 검증 실패")
                stats["failed"] += 1
    conn.commit()
    return stats


def publish_draft(conn: psycopg.Connection, s: Settings, embedder: Embedder, draft_id: int, now: datetime,
                  decision: str = "approved") -> int | None:
    """관리 화면 승인(approved) 또는 06:20 자동 게시(auto)."""
    with conn.transaction():
        d = conn.execute("SELECT * FROM drafts WHERE id = %s FOR UPDATE", (draft_id,)).fetchone()
        if d is None or d["post_seq"] is not None or d["status"] == "rejected":
            return None
        req = conn.execute("SELECT * FROM generation_requests WHERE id = %s", (d["request_id"],)).fetchone()
        seq = commit.publish(conn, s, embedder, req, d["payload"], d["verify_report"], now, review=decision)
        conn.execute("UPDATE drafts SET status = %s, post_seq = %s, decided_at = COALESCE(decided_at, %s) WHERE id = %s",
                     (decision, seq, now, draft_id))
        conn.execute("UPDATE generation_requests SET status = 'published' WHERE id = %s", (req["id"],))
        triggers.after_publish(conn, seq, now, s)
    conn.commit()
    return seq


def reject_draft(conn: psycopg.Connection, draft_id: int, reason: str, note: str | None, now: datetime) -> None:
    with conn.transaction():
        d = conn.execute("SELECT * FROM drafts WHERE id = %s FOR UPDATE", (draft_id,)).fetchone()
        if d is None or d["post_seq"] is not None:
            return
        conn.execute("UPDATE drafts SET status='rejected', reject_reason=%s, reject_note=%s, decided_at=%s WHERE id=%s",
                     (reason, note, now, draft_id))
        conn.execute("UPDATE generation_requests SET status='rejected' WHERE id=%s", (d["request_id"],))
        if d["cluster_id"]:
            conn.execute("UPDATE clusters SET state='skipped' WHERE id=%s AND state='open'", (d["cluster_id"],))
        log_decision(conn, "review", f"draft:{draft_id}", {"outcome": "rejected", "reason": reason, "note": note})
    conn.commit()


def auto_publish_pending(conn: psycopg.Connection, s: Settings, embedder: Embedder, now: datetime) -> list[int]:
    """06:20까지 손대지 않은 초안은 규칙 검증을 통과했으므로 자동 게시한다. 결정성을 위해 id 순서로."""
    ids = [r["id"] for r in conn.execute("SELECT id FROM drafts WHERE status = 'pending' ORDER BY id").fetchall()]
    out = []
    for i in ids:
        seq = publish_draft(conn, s, embedder, i, now, decision="auto")
        if seq:
            out.append(seq)
    return out
