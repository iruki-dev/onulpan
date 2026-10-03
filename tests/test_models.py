"""모델을 바꾸거나 모델이 은퇴해도 요청이 400 없이 나가고, 파이프라인이 멈추지 않는지."""
from __future__ import annotations

import pytest
from helpers import full_day

from worker.dev.fake import FakeLLM
from worker.generate import models, prompts
from worker.generate.gateway import ModelUnavailable
from worker.ops import compare


@pytest.fixture(autouse=True)
def clean_retired():
    models._retired_runtime.clear()
    yield
    models._retired_runtime.clear()


def P(model, **kw):
    return models.apply_thinking({"model": model, "max_tokens": 1500}, **kw)


def test_thinking_off_per_model():
    assert P("claude-sonnet-5")["thinking"] == {"type": "disabled"}
    p = P("claude-sonnet-5-5", effort="xhigh")
    assert p["thinking"] == {"type": "between_tools"}            # disabled는 400
    assert p["output_config"] == {"effort": "high"}              # between_tools는 high 이하만
    h = P("claude-haiku-4-5", effort="low")
    assert "thinking" not in h and "output_config" not in h      # Haiku 4.5는 effort를 받지 않는다
    o = P("claude-opus-5-5", headroom=4000)
    assert "thinking" not in o and o["output_config"] == {"effort": "low"} and o["max_tokens"] == 5500
    a = P("claude-sonnet-5-5", mode="adaptive", effort="low", headroom=4000)
    assert a["thinking"] == {"type": "adaptive"} and a["max_tokens"] == 5500
    assert P("claude-haiku-4-5-20251001")["max_tokens"] == 1500 and "thinking" not in P("claude-haiku-4-5-20251001")


def test_build_params_follows_model(s):
    s["generate"]["model"] = "claude-sonnet-5-5"
    p = prompts.build_params("fact", "본문", s)
    assert p["model"] == "claude-sonnet-5-5" and p["thinking"] == {"type": "between_tools"}
    s["generate"]["model"] = "claude-sonnet-5"
    assert prompts.build_params("fact", "본문", s)["thinking"] == {"type": "disabled"}
    s["generate"]["structured_output"] = True
    p = prompts.build_params("fact", "본문", s)
    assert p["output_config"]["format"]["type"] == "json_schema"   # effort 정리가 format을 지우지 않는다


class RetiredHaiku(FakeLLM):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.models = []

    def create(self, params):
        self.models.append((params["model"], params.get("thinking"), params.get("output_config")))
        if params["model"].startswith("claude-haiku"):
            raise ModelUnavailable(params["model"], "not_found_error")
        return super().create(params)


def test_light_model_falls_back_when_retired(conn, s, monkeypatch):
    delivered = []
    monkeypatch.setattr("worker.ops.alerts._deliver", lambda t: delivered.append(t) or True)
    llm = RetiredHaiku([])
    res = models.light_call(conn, llm, s, "verify", "너는 사실 확인 담당자다.", "<facts>0. x</facts>", 256)
    assert res is not None and res.ok and res.model == "claude-sonnet-5-5"
    assert llm.models[0][0] == "claude-haiku-4-5"
    assert llm.models[1] == ("claude-sonnet-5-5", {"type": "between_tools"}, {"effort": "low"})
    assert delivered and "claude-haiku-4-5" in delivered[0]
    assert conn.execute("SELECT count(*) AS n FROM llm_calls WHERE purpose='verify' AND model='claude-sonnet-5-5'").fetchone()["n"] == 1
    # 다음 프로세스: 알림 기록에서 은퇴를 불러와 처음부터 대체 모델로
    models._retired_runtime.clear()
    assert models.resolve("claude-haiku-4-5", s) == "claude-haiku-4-5"
    models.load_retired(conn)
    assert models.resolve("claude-haiku-4-5", s) == "claude-sonnet-5-5"
    llm.models.clear()
    models.light_call(conn, llm, s, "verify", "너는 사실 확인 담당자다.", "x", 256)
    assert [m[0] for m in llm.models] == ["claude-sonnet-5-5"]


def test_config_retired_list(s):
    s["models"]["retired"] = ["claude-sonnet-5"]
    assert prompts.build_params("fact", "본문", s)["model"] == "claude-sonnet-5-5"


def test_no_fallback_returns_none(conn, s, monkeypatch):
    monkeypatch.setattr("worker.ops.alerts._deliver", lambda t: True)
    s["models"]["fallbacks"] = {}
    assert models.light_call(conn, RetiredHaiku([]), s, "verify", "너는 사실 확인 담당자다.", "x", 256) is None


def test_compare_models_report(conn, s, now, tmp_path):
    _, emb, llm = full_day(conn, s, now)
    est = compare.estimate_usd([compare.parse_variant(x, s) for x in ("claude-sonnet-5", "claude-sonnet-5-5@adaptive/low")], 5)
    assert est > 0
    out = compare.run(conn, s, llm, emb, ["claude-sonnet-5", "claude-sonnet-5-5@adaptive/low"], 5, ["fact"], now,
                      out_dir=tmp_path)
    assert out["n_requests"] > 0
    a, b = out["summary"]["claude-sonnet-5"], out["summary"]["claude-sonnet-5-5@adaptive/low"]
    assert a["n"] == b["n"] == out["n_requests"] and a["errors"] == 0
    assert a["passed"] > 0 and a["chars_avg"] > 0
    text = open(out["report"], encoding="utf-8").read()
    assert "claude-sonnet-5-5@adaptive/low" in text and "검증 통과" in text
    sent = [c for c in llm.calls if c["model"] == "claude-sonnet-5-5"]
    assert sent and all(c["thinking"] == {"type": "adaptive"} and c["output_config"]["effort"] == "low" for c in sent)
    # 아무것도 게시하지 않는다
    assert conn.execute("SELECT count(*) AS n FROM llm_calls WHERE purpose='compare'").fetchone()["n"] == 2 * out["n_requests"]
