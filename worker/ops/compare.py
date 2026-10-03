"""생성 모델 비교: 최근 생성 요청의 입력을 그대로 여러 모델(·설정)에 다시 보내 분량·비용·검증 통과율을 견준다.

    python -m worker.jobs.cli compare-models claude-sonnet-5 claude-sonnet-5-5 [--n 10] [--kinds fact,synthesis] [--yes]
    python -m worker.jobs.cli compare-models claude-sonnet-5 claude-sonnet-5-5@adaptive/low --yes

모델 뒤 @생각/노력으로 설정을 바꿔 볼 수 있다 (기본은 config의 generate.thinking·effort).
아무것도 게시하지 않는다. 호출은 실제 API(즉시 호출, 정가)라 비용이 들며 llm_calls(purpose='compare')와 예산에 잡힌다.
--yes가 없으면 예상 비용만 보여 주고 끝낸다. 결과는 reports/model-compare-*.md.
"""
from __future__ import annotations

import copy
import statistics
import time
from datetime import datetime
from pathlib import Path

import psycopg

from ..generate import prompts
from ..generate.gateway import PRICING, LLMClient, budget_state, cost_usd, record_call
from ..nlp import char_count
from ..pipeline import build_context
from ..process.embed import Embedder
from ..settings import ROOT, Settings
from ..timeutil import kst
from ..verify.runner import run_rules

EST_INPUT, EST_OUTPUT = 9000, 1400          # 한 편 예상 토큰 (설계서 추정 + 입력 기사 6편)


def parse_variant(spec: str, s: Settings) -> dict:
    model, _, rest = spec.partition("@")
    mode, _, effort = rest.partition("/")
    return {"label": spec, "model": model, "thinking": mode or s["generate"].get("thinking", "disabled"),
            "effort": effort or s["generate"].get("effort")}


def sample_requests(conn: psycopg.Connection, kinds: list[str], n: int) -> list[dict]:
    return conn.execute(
        """SELECT id, kind::text AS kind, cluster_id, input FROM generation_requests
           WHERE attempt = 1 AND input IS NOT NULL AND kind::text = ANY(%s)
             AND status IN ('published','drafted','received','failed','retry','rejected')
           ORDER BY id DESC LIMIT %s""",
        (kinds, n),
    ).fetchall()


def estimate_usd(variants: list[dict], n: int) -> float:
    total = 0.0
    for v in variants:
        p = PRICING.get(v["model"], PRICING["claude-sonnet-5"])
        out = EST_OUTPUT * (3 if v["thinking"] == "adaptive" else 1)
        total += n * (EST_INPUT * p["input"] + out * p["output"]) / 1_000_000
    return round(total, 2)


def _in_range(kind: str, chars: int, s: Settings) -> bool:
    lo, hi = s["verify"]["lengths"]["body"].get(kind, [0, 10**9])
    tol = s["verify"]["lengths"]["tolerance"]
    return lo * (1 - tol) <= chars <= hi * (1 + tol)


def run(conn: psycopg.Connection, s: Settings, llm: LLMClient, embedder: Embedder, specs: list[str], n: int,
        kinds: list[str], now: datetime, out_dir: Path | None = None) -> dict:
    variants = [parse_variant(x, s) for x in specs]
    reqs = sample_requests(conn, kinds, n)
    rows: dict[str, list[dict]] = {v["label"]: [] for v in variants}
    for req in reqs:
        inp = req["input"]
        for v in variants:
            s2 = copy.deepcopy(s)
            s2["generate"].update(model=v["model"], thinking=v["thinking"], effort=v["effort"])
            params = prompts.build_params(req["kind"], inp["user_text"], s2)
            t0 = time.monotonic()
            try:
                res = llm.create(params)
            except RuntimeError as e:
                rows[v["label"]].append({"req": req["id"], "error": str(e)[:200]})
                continue
            secs = time.monotonic() - t0
            record_call(conn, "compare", res)
            conn.commit()
            try:
                parsed = prompts.parse_json_output(res.text) if res.ok else None
                response = {"parsed": parsed, "raw": res.text}
            except (ValueError, TypeError) as e:
                parsed, response = None, {"parsed": None, "raw": res.text, "parse_error": str(e)}
            fake_req = {"id": req["id"], "kind": req["kind"], "cluster_id": req["cluster_id"], "input": inp,
                        "response": response}
            report = run_rules(build_context(conn, fake_req, s, embedder, None))
            body = (parsed or {}).get("body_md") or ""
            rows[v["label"]].append({
                "req": req["id"], "kind": req["kind"], "ok": res.ok, "stop": res.stop_reason, "secs": secs,
                "passed": bool(report.get("passed")), "failed": [r["id"] for r in report["rules"] if not r["ok"]],
                "chars": char_count(body) if body else 0, "title": (parsed or {}).get("title", ""),
                "in_tokens": res.usage.input_tokens + res.usage.cache_creation_input_tokens + res.usage.cache_read_input_tokens,
                "out_tokens": res.usage.output_tokens,
                "cost": cost_usd(res.model or v["model"], res.usage), "batch_cost": cost_usd(res.model or v["model"], res.usage, batch=True),
            })
    summary = {}
    for label, rs in rows.items():
        good = [r for r in rs if "error" not in r]
        summary[label] = {
            "n": len(rs), "errors": len(rs) - len(good),
            "passed": sum(r["passed"] for r in good),
            "refusals": sum(r["stop"] == "refusal" for r in good),
            "truncated": sum(r["stop"] == "max_tokens" for r in good),
            "chars_avg": round(statistics.mean([r["chars"] for r in good]), 0) if good else 0,
            "in_range": sum(_in_range(r["kind"], r["chars"], s) for r in good if r["chars"]),
            "out_avg": round(statistics.mean([r["out_tokens"] for r in good]), 0) if good else 0,
            "cost_avg": round(statistics.mean([r["cost"] for r in good]), 5) if good else 0,
            "batch_cost_avg": round(statistics.mean([r["batch_cost"] for r in good]), 5) if good else 0,
            "secs_avg": round(statistics.mean([r["secs"] for r in good]), 1) if good else 0,
            "failed_rules": sorted({f for r in good for f in r["failed"]}),
        }
    path = write_report(out_dir or ROOT / "reports", variants, reqs, rows, summary, now)
    return {"report": str(path), "summary": summary, "n_requests": len(reqs)}


def write_report(out_dir: Path, variants: list[dict], reqs: list[dict], rows: dict, summary: dict, now: datetime) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = kst(now).strftime("%Y%m%d-%H%M")
    path = out_dir / f"model-compare-{stamp}.md"
    L = [f"# 생성 모델 비교 ({kst(now):%Y-%m-%d %H:%M} KST)", "",
         f"최근 생성 요청 {len(reqs)}건의 입력을 그대로 다시 보냈다(즉시 호출). 아무것도 게시하지 않았다.", "",
         "| 설정 | 검증 통과 | 분량 범위 안 | 본문 평균(자) | 출력 토큰 | 한 편 비용(배치 기준) | 응답 시간 | 거절·잘림·오류 | 실패한 규칙 |",
         "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for v in variants:
        m = summary[v["label"]]
        ok_n = m["n"] - m["errors"]
        L.append(f"| `{v['label']}` (생각 {v['thinking']}{'/' + v['effort'] if v['effort'] else ''}) "
                 f"| {m['passed']}/{ok_n} | {m['in_range']}/{ok_n} | {m['chars_avg']:.0f} | {m['out_avg']:.0f} "
                 f"| ${m['batch_cost_avg']:.4f} (즉시 ${m['cost_avg']:.4f}) | {m['secs_avg']}초 "
                 f"| {m['refusals']}·{m['truncated']}·{m['errors']} | {', '.join(m['failed_rules']) or '—'} |")
    L += ["", "월 비용 어림: 한 편 배치 비용 × 하루 편수(베타 30, 출시 150) × 30일.", "",
          "## 글별 제목", "", "| 요청 | " + " | ".join(f"`{v['label']}`" for v in variants) + " |",
          "| --- | " + " | ".join("---" for _ in variants) + " |"]
    for req in reqs:
        cells = []
        for v in variants:
            r = next((x for x in rows[v["label"]] if x["req"] == req["id"]), None)
            if r is None or "error" in r:
                cells.append("오류")
            else:
                mark = "✓" if r["passed"] else "✕ " + ",".join(r["failed"])
                cells.append(f"{r['title']} ({r['chars']}자, {mark})")
        L.append(f"| #{req['id']} {req['kind']} | " + " | ".join(cells) + " |")
    L += ["", "판단은 사람이 한다: 검증 통과율이 같거나 높고 분량이 범위 안이면 config/beta.yaml의 generate.model을 바꾼다."]
    path.write_text("\n".join(L) + "\n", encoding="utf-8")
    return path


def budget_ok(conn: psycopg.Connection, s: Settings, estimate: float) -> tuple[bool, str]:
    b = budget_state(conn, s)
    if b.blocked or b.spent + estimate > b.limit:
        return False, f"예산 부족: 이번 달 ${b.spent:.2f} / ${b.limit:.2f}, 예상 ${estimate:.2f}"
    return True, f"이번 달 ${b.spent:.2f} / ${b.limit:.2f}, 예상 ${estimate:.2f}"
