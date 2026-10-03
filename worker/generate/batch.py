"""5단계 제출과 회수.

사실 글은 Message Batches로 모아 제출한다(50% 할인, 보통 1시간 안에 완료). 1면 후보와 속보성 묶음만 즉시 호출한다.
배치가 24시간 안에 안 끝나면 취소 후 즉시 호출로 재제출한다.
LLM이 멈추거나 월 예산 상한에 이르면 제출하지 않고 대기열(pending)에 쌓는다. 복구되면 중요도 순으로 처리한다.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

import psycopg

from ..db import jsonb, log_decision
from ..settings import Settings
from . import prompts
from .gateway import LLMClient, LLMResult, budget_state, record_call

log = logging.getLogger(__name__)


def prepare(conn: psycopg.Connection, req: dict, s: Settings) -> dict:
    """요청 하나의 입력 문서와 사용자 메시지를 만든다. 재생성 요청은 부모의 입력을 그대로 쓴다."""
    if req["parent_id"]:
        parent = conn.execute("SELECT input FROM generation_requests WHERE id = %s", (req["parent_id"],)).fetchone()
        return parent["input"]
    kind = str(req["kind"])
    g = s["generate"]
    docs: list[prompts.Doc] = []
    related: list[dict] = []
    spec: dict = {}
    slugs: list[str] = []
    if kind in ("fact", "issue"):
        cl = conn.execute("SELECT * FROM clusters WHERE id = %s", (req["cluster_id"],)).fetchone()
        docs = prompts.pick_articles(conn, cl["id"], s)
        related = prompts.related_posts(conn, cl["id"], cl["slug"], g["related_posts"])
        slugs = prompts.existing_slugs(conn, cl["id"])
    elif kind == "synthesis":
        slug = req["slug"]
        last = conn.execute(
            "SELECT * FROM posts WHERE slug = %s AND kind = 'synthesis' ORDER BY seq DESC LIMIT 1", (slug,)
        ).fetchone()
        after = last["seq"] if last else 0
        facts = conn.execute(
            """SELECT * FROM posts WHERE slug = %s AND kind IN ('fact','correction') AND seq > %s
               ORDER BY seq DESC LIMIT 8""",
            (slug, after),
        ).fetchall()
        rows = ([last] if last else []) + sorted(facts, key=lambda r: r["seq"])
        docs = [prompts.post_doc(conn, r) for r in rows]
        spec = {"slug": slug}
        slugs = [slug]
    elif kind == "explainer":
        rows = conn.execute(
            """SELECT p.* FROM term_mentions t JOIN posts p ON p.seq = t.post_seq
               WHERE t.term = %s ORDER BY p.seq DESC LIMIT 6""",
            (req["term"],),
        ).fetchall()
        docs = [prompts.post_doc(conn, r) for r in sorted(rows, key=lambda r: r["seq"])]
        spec = {"term": req["term"]}
    elif kind == "culture":
        spec = {"title": req["topic"]["title"], "area": req["topic"].get("area", "")}
    terms = prompts.known_terms(conn)
    user_text = prompts.render_user(kind, docs, related, terms, slugs, spec)
    return {
        "docs": [d.to_json() for d in docs],
        "related": [r["seq"] for r in related],
        "spec": spec,
        "user_text": user_text,
        "prompt_version": prompts.prompt_version(kind),
    }


def _params_for(req: dict, inp: dict, s: Settings) -> dict:
    retry = None
    if req["attempt"] == 2 and req["feedback"]:
        retry = req["feedback"]
    return prompts.build_params(str(req["kind"]), inp["user_text"], s, retry=retry)


def store_result(conn: psycopg.Connection, req_id: int, kind: str, result: LLMResult, now: datetime,
                 batch_id: str | None = None) -> None:
    cost = record_call(conn, f"generate_{kind}", result, batch_id)
    if result.ok:
        try:
            parsed = prompts.parse_json_output(result.text)
            response = {"parsed": parsed, "raw": result.text}
        except (ValueError, TypeError) as e:
            response = {"parsed": None, "raw": result.text, "parse_error": str(e)}
    else:
        response = {"parsed": None, "raw": result.text, "error": result.error}
    conn.execute(
        """UPDATE generation_requests SET status = 'received', response = %s, model = %s,
             input_tokens = %s, output_tokens = %s, cost_usd = cost_usd + %s, finished_at = %s
           WHERE id = %s""",
        (jsonb(response), result.model or None,
         result.usage.input_tokens + result.usage.cache_creation_input_tokens + result.usage.cache_read_input_tokens,
         result.usage.output_tokens, cost, now, req_id),
    )


def submit_pending(conn: psycopg.Connection, llm: LLMClient, s: Settings, now: datetime,
                   kinds: tuple[str, ...] | None = None, immediate_only: bool = False) -> dict:
    stats = {"immediate": 0, "batched": 0, "held": 0, "batch_id": None}
    budget = budget_state(conn, s)
    q = "SELECT * FROM generation_requests WHERE status = 'pending'"
    args: list = []
    if kinds:
        q += " AND kind = ANY(%s::post_kind[])"
        args.append(list(kinds))
    if immediate_only:
        q += " AND mode = 'immediate'"
    q += " ORDER BY priority DESC, id"
    pending = conn.execute(q, args).fetchall()
    if budget.blocked:
        stats["held"] = len(pending)
        if pending:
            log_decision(conn, "budget_hold", f"month:{now:%Y-%m}", {"spent": budget.spent, "limit": budget.limit,
                                                                      "held": len(pending)})
        conn.commit()
        return stats

    batch_reqs: list[tuple[str, dict]] = []
    batch_ids: list[int] = []
    for req in pending:
        inp = prepare(conn, req, s)
        if str(req["kind"]) in ("fact", "issue") and len(inp["docs"]) < 2:
            # 기사 본문이 지워졌거나 부족: 출처 2곳 원칙을 지킬 수 없으므로 버린다
            conn.execute("UPDATE generation_requests SET status='discarded', input=%s, finished_at=%s WHERE id=%s",
                         (jsonb(inp), now, req["id"]))
            continue
        params = _params_for(req, inp, s)
        custom_id = f"g{req['id']}-a{req['attempt']}"
        conn.execute(
            """UPDATE generation_requests SET input = %s, prompt_version = %s, model = %s, custom_id = %s
               WHERE id = %s""",
            (jsonb(inp), inp["prompt_version"], params["model"], custom_id, req["id"]),
        )
        if req["mode"] == "immediate":
            conn.execute("UPDATE generation_requests SET status='submitted', submitted_at=%s WHERE id=%s", (now, req["id"]))
            conn.commit()
            try:
                result = llm.create(params)
            except RuntimeError as e:
                # API 장애: 생성만 멈춘다. 대기열로 되돌린다.
                log.warning("immediate call failed: %s", e)
                conn.execute("UPDATE generation_requests SET status='pending', submitted_at=NULL WHERE id=%s", (req["id"],))
                conn.commit()
                break
            store_result(conn, req["id"], str(req["kind"]), result, now)
            conn.commit()
            stats["immediate"] += 1
        else:
            batch_reqs.append((custom_id, params))
            batch_ids.append(req["id"])
    if batch_reqs:
        try:
            batch_id = llm.batch_create(batch_reqs)
        except RuntimeError as e:
            log.warning("batch submit failed: %s", e)
            conn.commit()
            return stats
        conn.execute("INSERT INTO llm_batches (batch_id, n_requests, submitted_at) VALUES (%s, %s, %s)",
                     (batch_id, len(batch_reqs), now))
        conn.execute(
            "UPDATE generation_requests SET status='submitted', submitted_at=%s, batch_id=%s WHERE id = ANY(%s)",
            (now, batch_id, batch_ids),
        )
        stats["batched"] = len(batch_reqs)
        stats["batch_id"] = batch_id
    conn.commit()
    return stats


def collect_batches(conn: psycopg.Connection, llm: LLMClient, s: Settings, now: datetime) -> dict:
    stats = {"collected": 0, "results": 0, "timed_out": 0}
    timeout = timedelta(hours=s["generate"]["batch_timeout_hours"])
    for b in conn.execute("SELECT * FROM llm_batches WHERE status IN ('in_progress','ended') ORDER BY submitted_at").fetchall():
        try:
            status = llm.batch_status(b["batch_id"])
        except RuntimeError as e:
            log.warning("batch status failed: %s", e)
            continue
        if status != "ended":
            if now - b["submitted_at"] > timeout:
                llm.batch_cancel(b["batch_id"])
                conn.execute("UPDATE llm_batches SET status='canceled', collected_at=%s WHERE batch_id=%s", (now, b["batch_id"]))
                conn.execute(
                    """UPDATE generation_requests SET status='pending', mode='immediate', batch_id=NULL, submitted_at=NULL
                       WHERE batch_id = %s AND status = 'submitted'""",
                    (b["batch_id"],),
                )
                stats["timed_out"] += 1
                conn.commit()
            continue
        by_custom = {
            r["custom_id"]: r for r in conn.execute(
                "SELECT id, kind::text AS kind, custom_id FROM generation_requests WHERE batch_id = %s", (b["batch_id"],)
            ).fetchall()
        }
        for custom_id, result in llm.batch_results(b["batch_id"]):
            req = by_custom.get(custom_id)
            if req is None:
                continue
            if not result.ok and result.error in ("errored", "expired", "canceled"):
                # 서버 쪽 실패는 재제출 대상 (검증 실패가 아니다)
                conn.execute("UPDATE generation_requests SET status='pending', batch_id=NULL WHERE id=%s", (req["id"],))
                continue
            store_result(conn, req["id"], req["kind"], result, now, batch_id=b["batch_id"])
            stats["results"] += 1
        conn.execute("UPDATE llm_batches SET status='collected', collected_at=%s WHERE batch_id=%s", (now, b["batch_id"]))
        stats["collected"] += 1
        conn.commit()
    return stats
