"""모델별 요청 차이와 은퇴 대비를 한곳에서 처리한다.

설정은 ‘무엇을 원하는지’(생각 끔/켬, 노력 수준)만 적고, 모델이 받는 형태로 바꾸는 일은 여기서 한다.
모델을 바꿔도 같은 설정이 400 없이 나가야 한다.

| 모델              | 생각 끔                     | effort        |
| claude-sonnet-5   | thinking: disabled          | 받음          |
| claude-sonnet-5-5 | thinking: between_tools (disabled는 400) · effort high 이하만 | 받음 |
| claude-opus-5-5   | 끌 수 없음 → effort low      | 받음          |
| claude-haiku-4-5  | thinking 생략(기본이 끔)     | 보내면 오류   |

은퇴: 모델이 404(없는 모델)를 돌려주면 models.fallbacks의 다음 모델로 바꿔 부르고 창업자에게 한 번 알린다.
같은 프로세스 안에서는 기억하고, 영구히 바꾸려면 config의 models.retired에 적는다.
"""
from __future__ import annotations

import logging

import psycopg

from ..settings import Settings
from .gateway import LLMClient, LLMResult, ModelUnavailable, record_call

log = logging.getLogger(__name__)

NO_EFFORT = ("claude-haiku-4-5",)
NO_THINKING_PARAM = ("claude-haiku-4-5",)            # thinking을 생략하면 끔
CANNOT_DISABLE = ("claude-opus-5-5", "claude-fable-5-1", "claude-fable-5")
BETWEEN_TOOLS = ("claude-sonnet-5-5",)
EFFORT_ORDER = ["low", "medium", "high", "xhigh", "max"]

_retired_runtime: set[str] = set()


def _base(model: str) -> str:
    """날짜가 붙은 전체 ID도 별칭으로 본다 (claude-haiku-4-5-20251001 → claude-haiku-4-5)."""
    for k in (*NO_EFFORT, *CANNOT_DISABLE, *BETWEEN_TOOLS, "claude-sonnet-5", "claude-opus-5"):
        if model == k or model.startswith(k + "-2"):
            return k
    return model


def apply_thinking(params: dict, mode: str = "disabled", effort: str | None = None, headroom: int = 0) -> dict:
    """params["model"]에 맞춰 thinking·output_config.effort를 채운다. mode: disabled | adaptive."""
    out = dict(params)
    model = _base(out["model"])
    out.pop("thinking", None)
    oc = dict(out.get("output_config") or {})
    oc.pop("effort", None)
    if model in NO_THINKING_PARAM:
        effort = None
    elif mode == "disabled":
        if model in BETWEEN_TOOLS:
            out["thinking"] = {"type": "between_tools"}
            if effort and EFFORT_ORDER.index(effort) > EFFORT_ORDER.index("high"):
                effort = "high"                     # between_tools는 high 이하만
        elif model in CANNOT_DISABLE:
            effort = "low"                          # 끌 수 없으면 가장 낮은 노력으로
            out["max_tokens"] = int(out["max_tokens"]) + headroom
        else:
            out["thinking"] = {"type": "disabled"}
    else:
        out["thinking"] = {"type": "adaptive"}
        out["max_tokens"] = int(out["max_tokens"]) + headroom   # 생각도 max_tokens에 들어간다
    if effort:
        oc["effort"] = effort
    if oc:
        out["output_config"] = oc
    else:
        out.pop("output_config", None)
    return out


def load_retired(conn: psycopg.Connection) -> set[str]:
    """이전 실행에서 404로 확인한 모델(알림 기록 model_retired:*)을 불러온다. 작업마다 프로세스가 새로 뜨기 때문."""
    rows = conn.execute("SELECT key FROM alerts_sent WHERE key LIKE 'model_retired:%'").fetchall()
    _retired_runtime.update(r["key"].split(":", 1)[1] for r in rows)
    conn.commit()
    return set(_retired_runtime)


def resolve(model: str, s: Settings) -> str:
    """은퇴한 모델이면 대체 모델로. 대체 모델이 또 은퇴했으면 그다음으로."""
    cfg = s.get("models") or {}
    retired = set(cfg.get("retired") or []) | _retired_runtime
    fallbacks = cfg.get("fallbacks") or {}
    seen = set()
    while model in retired and model in fallbacks and model not in seen:
        seen.add(model)
        model = fallbacks[model]
    return model


def mark_retired(conn: psycopg.Connection | None, model: str, s: Settings) -> str | None:
    """404를 받은 모델을 은퇴로 기억하고 대체 모델을 돌려준다. 대체가 없으면 None."""
    _retired_runtime.add(model)
    nxt = resolve(model, s)
    msg = (f"모델 {model}을(를) 쓸 수 없습니다(404, 은퇴 추정). "
           + (f"{nxt}로 바꿔 부릅니다. config의 models.retired에 {model}을 적어 두세요." if nxt != model
              else "대체 모델이 없어 이 호출을 건너뜁니다. config의 models.fallbacks를 확인하세요."))
    log.warning(msg)
    if conn is not None:
        from ..ops import alerts

        alerts.alert(conn, "model_retired", model, msg)
    return nxt if nxt != model else None


def light_call(conn: psycopg.Connection, llm: LLMClient, s: Settings, purpose: str, system: str,
               content: str | list, max_tokens: int) -> LLMResult | None:
    """검증(V11)·회색 구간 판정·이미지 검색어·사진 대조처럼 짧은 판정 호출. 생각은 끄고 노력은 낮게."""
    cfg = s.get("models") or {}
    model = resolve(cfg.get("light", "claude-haiku-4-5"), s)
    for _ in range(3):
        params = apply_thinking({"model": model, "max_tokens": max_tokens, "system": system,
                                 "messages": [{"role": "user", "content": content}]},
                                mode="disabled", effort=cfg.get("light_effort", "low"))
        try:
            res = llm.create(params)
        except ModelUnavailable:
            nxt = mark_retired(conn, model, s)
            if nxt is None:
                return None
            model = nxt
            continue
        except RuntimeError as e:
            log.warning("%s call failed: %s", purpose, e)
            return None
        record_call(conn, purpose, res)
        return res
    return None
