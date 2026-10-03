"""LLM 게이트웨이: 프롬프트 제출(즉시·배치), 비용 기록(llm_calls), 예산 차단기.

LLM 호출은 반드시 API 키로 한다. 운영 환경(ONULPAN_ENV=production)에서는 ANTHROPIC_API_KEY 외의
인증 수단(구독 OAuth 토큰, 다른 공급자 키)이 환경에 있으면 시작하지 않는다.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Iterable, Protocol

import psycopg

from ..timeutil import now as utcnow

# 1백만 토큰당 USD (Anthropic 1자 API 표준 가격). 배치는 50% 할인.
PRICING = {
    "claude-sonnet-5": {"input": 2.00, "output": 10.00},
    "claude-sonnet-5-5": {"input": 2.00, "output": 10.00},
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00},
    "claude-opus-5-5": {"input": 4.00, "output": 20.00},
}
CACHE_WRITE = 1.25
CACHE_READ = 0.10
BATCH_DISCOUNT = 0.5

FORBIDDEN_ENV = ("ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN", "NVIDIA_API_KEY", "NGC_API_KEY")


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


@dataclass
class LLMResult:
    text: str
    model: str
    usage: Usage = field(default_factory=Usage)
    stop_reason: str | None = None
    ok: bool = True
    error: str | None = None


def cost_usd(model: str, u: Usage, batch: bool = False) -> float:
    p = PRICING.get(model)
    if p is None:
        base = next((v for k, v in PRICING.items() if model.startswith(k)), PRICING["claude-sonnet-5"])
        p = base
    c = (
        u.input_tokens * p["input"]
        + u.cache_creation_input_tokens * p["input"] * CACHE_WRITE
        + u.cache_read_input_tokens * p["input"] * CACHE_READ
        + u.output_tokens * p["output"]
    ) / 1_000_000
    return round(c * (BATCH_DISCOUNT if batch else 1.0), 5)


class LLMClient(Protocol):
    def create(self, params: dict) -> LLMResult: ...
    def batch_create(self, requests: list[tuple[str, dict]]) -> str: ...
    def batch_status(self, batch_id: str) -> str: ...
    def batch_results(self, batch_id: str) -> Iterable[tuple[str, LLMResult]]: ...
    def batch_cancel(self, batch_id: str) -> None: ...


def check_credentials_policy() -> None:
    if os.environ.get("ONULPAN_ENV") != "production":
        return
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("운영 환경에는 ANTHROPIC_API_KEY가 필요하다")
    bad = [k for k in FORBIDDEN_ENV if os.environ.get(k)]
    if bad:
        raise RuntimeError(f"운영 환경 변수에는 Anthropic API 키만 둔다. 제거할 것: {', '.join(bad)}")


def _text_of(message: Any) -> str:
    return "".join(b.text for b in message.content if getattr(b, "type", None) == "text")


def _usage_of(message: Any) -> Usage:
    u = message.usage
    return Usage(
        input_tokens=u.input_tokens or 0,
        output_tokens=u.output_tokens or 0,
        cache_creation_input_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
        cache_read_input_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
    )


class AnthropicLLM:
    """Anthropic Python SDK. 사실 글은 Message Batches로 모아 제출한다."""

    def __init__(self) -> None:
        check_credentials_policy()
        import anthropic

        self._anthropic = anthropic
        key = os.environ.get("ANTHROPIC_API_KEY")
        self.client = anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()

    def create(self, params: dict) -> LLMResult:
        try:
            msg = self.client.messages.create(**params)
        except self._anthropic.BadRequestError as e:
            return LLMResult(text="", model=params["model"], ok=False, error=f"bad_request: {e}")
        except self._anthropic.APIStatusError as e:
            raise RuntimeError(f"llm status {e.status_code}: {e}") from e
        except self._anthropic.APIConnectionError as e:
            raise RuntimeError(f"llm connection: {e}") from e
        if msg.stop_reason == "refusal":
            return LLMResult(text="", model=msg.model, usage=_usage_of(msg), stop_reason="refusal", ok=False, error="refusal")
        return LLMResult(text=_text_of(msg), model=msg.model, usage=_usage_of(msg), stop_reason=msg.stop_reason)

    def batch_create(self, requests: list[tuple[str, dict]]) -> str:
        from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
        from anthropic.types.messages.batch_create_params import Request

        batch = self.client.messages.batches.create(
            requests=[Request(custom_id=cid, params=MessageCreateParamsNonStreaming(**p)) for cid, p in requests]
        )
        return batch.id

    def batch_status(self, batch_id: str) -> str:
        return self.client.messages.batches.retrieve(batch_id).processing_status

    def batch_results(self, batch_id: str) -> Iterable[tuple[str, LLMResult]]:
        for r in self.client.messages.batches.results(batch_id):
            if r.result.type == "succeeded":
                m = r.result.message
                ok = m.stop_reason != "refusal"
                yield r.custom_id, LLMResult(text=_text_of(m), model=m.model, usage=_usage_of(m),
                                             stop_reason=m.stop_reason, ok=ok, error=None if ok else "refusal")
            else:
                yield r.custom_id, LLMResult(text="", model="", ok=False, error=r.result.type)

    def batch_cancel(self, batch_id: str) -> None:
        self.client.messages.batches.cancel(batch_id)


# ── 비용 기록과 예산 차단기 ──────────────────────────────

def record_call(conn: psycopg.Connection, purpose: str, result: LLMResult, batch_id: str | None = None) -> float:
    c = cost_usd(result.model or "claude-sonnet-5", result.usage, batch=batch_id is not None)
    conn.execute(
        """INSERT INTO llm_calls (purpose, model, batch_id, input_tokens, output_tokens, cost_usd)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (purpose, result.model or "unknown", batch_id,
         result.usage.input_tokens + result.usage.cache_creation_input_tokens + result.usage.cache_read_input_tokens,
         result.usage.output_tokens, c),
    )
    return c


def month_cost(conn: psycopg.Connection) -> float:
    row = conn.execute(
        """SELECT COALESCE(sum(cost_usd), 0) AS c FROM llm_calls
           WHERE date_trunc('month', at AT TIME ZONE 'Asia/Seoul') = date_trunc('month', now() AT TIME ZONE 'Asia/Seoul')"""
    ).fetchone()
    return float(row["c"])


@dataclass
class BudgetState:
    spent: float
    limit: float

    @property
    def ratio(self) -> float:
        return self.spent / self.limit if self.limit > 0 else 1.0

    @property
    def blocked(self) -> bool:
        return self.ratio >= 1.0


def budget_state(conn: psycopg.Connection, s) -> BudgetState:
    return BudgetState(spent=month_cost(conn), limit=float(s["budget"]["monthly_usd"]))


def stamp() -> str:
    return utcnow().strftime("%Y%m%dT%H%M%S")
