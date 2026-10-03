"""규칙별 단위 테스트: 틀린 초안 픽스처로 검증기가 잡는지 확인한다 (DB 없이)."""
import copy
from datetime import datetime, timezone

import pytest

from worker.dev.fake import build_events, _subst
from worker.process.embed import HashingEmbedder
from worker.settings import load_settings
from worker.verify.base import Context
from worker.verify.runner import run_rules

BASE = datetime(2026, 10, 6, 3, 0, tzinfo=timezone.utc)
OUTLET_IDS = {"가상일보": 1, "가상방송": 2, "가상통신": 3, "가상경제": 4, "가상지역신문": 5}
EMB = HashingEmbedder()


def make_ctx(key="누리전자", kind="fact", mutate=None, settings=None, judge=None):
    ev = next(e for e in build_events(BASE) if e["key"] == key)
    docs, mapping = {}, {}
    for i, a in enumerate(ev["articles"]):
        if a["outlet"] in mapping:  # 통신 전재 중복은 입력에서 빠진다
            continue
        if a["outlet"] == "가상지역신문" and key == "누리전자":
            continue
        rid = f"r_{i + 1}"
        mapping[a["outlet"]] = rid
        docs[rid] = {"id": rid, "kind": "raw", "text": f"제목: {a['title']}\n본문: {a['body'][:1500]}",
                     "outlet_ids": [OUTLET_IDS[a["outlet"]]], "raw_ids": [i + 1], "outlet": a["outlet"],
                     "published": "2026-10-06T09:00+09:00"}
    draft = _subst(copy.deepcopy(ev["drafts"][kind]), mapping)
    if mutate:
        mutate(draft, docs)
    return Context(kind=kind, draft=draft, raw_text="", docs=docs, s=settings or load_settings("beta"),
                   names=set(OUTLET_IDS), embed=EMB.embed, embedder_name=EMB.name, semantic_judge=judge)


def failed(report):
    return {r["id"] for r in report["rules"] if not r["ok"]}


@pytest.mark.parametrize("key,kind", [("누리전자", "fact"), ("물류창고", "fact"), ("예산안", "fact"),
                                      ("예산안", "issue"), ("노르벤", "fact"), ("전고체", "fact")])
def test_good_drafts_pass(key, kind):
    report = run_rules(make_ctx(key, kind))
    assert report["passed"], [r for r in report["rules"] if not r["ok"]]


def _body(d, f):
    d["body_md"] = f(d["body_md"])


def test_v1_parse_failure():
    ctx = make_ctx()
    ctx.draft, ctx.parse_error = None, "JSON 객체를 찾지 못함"
    report = run_rules(ctx)
    assert failed(report) == {"V1"} and report["action"] == "regen"


@pytest.mark.parametrize("mut", [
    lambda d, _: d.update(title="누리전자 3분기 영업이익이 크게 늘었다는 소식이 전해졌다 시장 반응은?"),
    lambda d, _: d.update(summary="가" * 81),
    lambda d, _: _body(d, lambda b: b[:200]),
    lambda d, _: _body(d, lambda b: "## 제목\n" + b),
    lambda d, _: d.pop("facts"),
    lambda d, _: d.update(section="sports"),
])
def test_v1_schema(mut):
    assert "V1" in failed(run_rules(make_ctx(mutate=mut)))


def test_v2_single_outlet_is_discarded():
    def mut(d, docs):
        only = next(iter(docs))
        for k in list(docs)[1:]:
            docs.pop(k)
        for f in d["facts"]:
            f["source_ids"] = [only]
    report = run_rules(make_ctx(mutate=mut))
    assert "V2" in failed(report) and report["action"] == "discard"


def test_v2_unknown_source_id():
    def mut(d, _):
        d["facts"][0]["source_ids"] = ["r_999"]
    report = run_rules(make_ctx(mutate=mut))
    assert "V2" in failed(report) and report["action"] == "regen"


def test_v3_wrong_number():
    report = run_rules(make_ctx(mutate=lambda d, _: _body(d, lambda b: b.replace("1조2000억원", "1조3000억원", 1))))
    assert "V3" in failed(report)
    msg = next(r for r in report["rules"] if r["id"] == "V3")["messages"]
    assert any("1조3000억원" in m for m in msg)


def test_v3_accepts_equivalent_spelling():
    report = run_rules(make_ctx(mutate=lambda d, _: _body(d, lambda b: b.replace("12%", "12퍼센트"))))
    assert "V3" not in failed(report)


@pytest.mark.parametrize("text", ["어제", "지난주", "오늘", "이번 주"])
def test_v4_relative_dates(text):
    report = run_rules(make_ctx(mutate=lambda d, _: _body(d, lambda b: b.replace("공시 직후", f"{text} 공시 직후"))))
    assert "V4" in failed(report)


def test_v4_wrong_absolute_date():
    report = run_rules(make_ctx(mutate=lambda d, _: _body(d, lambda b: b.replace("10월 6일", "10월 9일"))))
    assert "V4" in failed(report)


def test_v5_unknown_proper_noun():
    report = run_rules(make_ctx(mutate=lambda d, _: _body(d, lambda b: b.replace("이하준 대표는", "김철수 대표는"))))
    assert "V5" in failed(report)


def test_v6_misquote():
    def mut(d, _):
        d["quotes"][0]["text"] = "메모리 수요가 폭발적으로 늘고 있다"
        d["body_md"] = d["body_md"].replace("뚜렷하게 회복되고", "폭발적으로 늘고")
    assert "V6" in failed(run_rules(make_ctx(mutate=mut)))


def test_v6_speaker_not_in_source():
    def mut(d, _):
        d["quotes"][0]["speaker"] = "박영희 사장"
    assert "V6" in failed(run_rules(make_ctx(mutate=mut)))


def test_v6_too_many_quotes():
    def mut(d, _):
        d["quotes"] = d["quotes"] * 3
    assert "V6" in failed(run_rules(make_ctx(mutate=mut)))


def test_v7_copied_sentences():
    def mut(d, docs):
        src = next(iter(docs.values()))["text"].split("본문: ", 1)[1]
        d["body_md"] = src.replace("\n", " ") + "\n\n" + d["body_md"][:150]
    report = run_rules(make_ctx(mutate=mut))
    assert "V7" in failed(report)


@pytest.mark.parametrize("phrase", ["논란이 일고 있다", "비판이 나온다", "우려가 제기된다", "충격적인 결과다", "귀추가 주목된다"])
def test_v8_banned(phrase):
    report = run_rules(make_ctx(mutate=lambda d, _: _body(d, lambda b: b + f" 이를 두고 {phrase}.")))
    assert "V8" in failed(report)


def test_v8_allows_inside_quotes():
    def mut(d, _):
        d["quotes"][0]["text"] = "메모리 수요가 뚜렷하게 회복되고 있다"
    assert "V8" not in failed(run_rules(make_ctx(mutate=mut)))


def test_v9_missing_conflicts():
    report = run_rules(make_ctx("물류창고", mutate=lambda d, _: d.update(conflicts=[])))
    assert "V9" in failed(report)


def test_v9_no_false_positive_on_consistent_numbers():
    assert "V9" not in failed(run_rules(make_ctx("누리전자")))


def test_v10_unbacked_sentence():
    def mut(d, _):
        d["body_md"] += " 회사는 메모리 공장 증설을 내년에 끝낼 계획이라고 덧붙였다."
    assert "V10" in failed(run_rules(make_ctx(mutate=mut)))


def test_v11_semantic_only_in_launch_mode():
    calls = []

    def judge(facts, sources):
        calls.append(facts)
        return [{"index": 0, "reason": "원문은 공시가 아니라 보도"}]

    beta = run_rules(make_ctx(judge=judge))
    assert beta["passed"] and not calls
    launch = run_rules(make_ctx(settings=load_settings("launch"), judge=judge))
    assert "V11" in failed(launch) and calls


def test_v11_skipped_when_rules_already_failed():
    calls = []
    run_rules(make_ctx(settings=load_settings("launch"), judge=lambda f, s: calls.append(1) or [],
                       mutate=lambda d, _: _body(d, lambda b: b + " 논란이 일고 있다.")))
    assert not calls
