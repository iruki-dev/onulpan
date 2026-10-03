"""파이프라인 끝에서 끝까지: 수집 → 중복 제거 → 묶기 → 선정 → 생성(가짜 LLM) → 검증 → 초안 → 게시 → 링크."""
from datetime import timedelta

from worker.dev.fake import FakeLLM
from worker.generate import batch
from worker.generate.gateway import cost_usd, Usage
from worker.pipeline import process_received, publish_draft, reject_draft

from helpers import full_day, run_generation, setup_day


def test_dedup_and_clustering(conn, s, now):
    setup_day(conn, s, now)
    dup = conn.execute(
        "SELECT r.duplicate_of, o.name FROM raw_articles r JOIN outlets o ON o.id = r.outlet_id WHERE r.duplicate_of IS NOT NULL"
    ).fetchall()
    assert [d["name"] for d in dup] == ["가상지역신문"]  # 통신 전재
    clusters = conn.execute("SELECT n_articles, n_outlets, n_groups FROM clusters ORDER BY id").fetchall()
    assert len(clusters) == 6
    nuri = clusters[0]
    assert nuri["n_articles"] == 4 and nuri["n_outlets"] == 4 and nuri["n_groups"] == 4
    assigns = conn.execute("SELECT count(*) AS n FROM decision_log WHERE kind = 'assign'").fetchone()["n"]
    assert assigns == 15  # 모든 배정 판단이 기록된다


def test_selection_skips_single_outlet(conn, s, now):
    setup_day(conn, s, now)
    from worker.process.select import select_targets

    ids = select_targets(conn, now, s)
    assert len(ids) == 5
    picked = conn.execute(
        """SELECT DISTINCT r.title FROM generation_requests g JOIN raw_articles r ON r.cluster_id = g.cluster_id"""
    ).fetchall()
    assert not any("가을축제" in p["title"] for p in picked)
    modes = [r["mode"] for r in conn.execute("SELECT mode FROM generation_requests ORDER BY priority DESC").fetchall()]
    assert modes == ["immediate"] * 5  # 상위 5편은 1면 후보로 즉시 호출


def test_daily_cap(conn, s, now):
    setup_day(conn, s, now)
    from worker.process.select import select_targets

    s["select"]["daily_cap"] = 2
    assert len(select_targets(conn, now, s)) == 2
    assert select_targets(conn, now + timedelta(hours=1), s) == []


def test_beta_goes_through_drafts_then_publishes(conn, s, now):
    full_day(conn, s, now)
    drafts = conn.execute("SELECT status FROM drafts").fetchall()
    assert {d["status"] for d in drafts} == {"auto"}
    posts = conn.execute("SELECT * FROM posts ORDER BY seq").fetchall()
    assert len(posts) == 5
    for p in posts:
        outlets = conn.execute("SELECT count(DISTINCT outlet_id) AS n FROM post_sources WHERE post_seq = %s",
                               (p["seq"],)).fetchone()["n"]
        assert outlets >= 2, p["title"]  # 모든 글은 출처 2곳 이상
        assert p["model"] and p["prompt_version"].startswith("system.v1+fact.v1")
        assert p["verify_report"]["passed"] is True
        assert p["meta"]["review"] == "auto"
    fire = next(p for p in posts if "화재" in p["title"])
    assert fire["meta"]["conflicts"][0]["field"] == "사망자 수"
    assert conn.execute("SELECT count(*) AS n FROM clusters WHERE state = 'written'").fetchone()["n"] == 5


def test_launch_publishes_directly(conn, s_launch, now):
    full_day(conn, s_launch, now)
    assert conn.execute("SELECT count(*) AS n FROM drafts").fetchone()["n"] == 0
    assert conn.execute("SELECT count(*) AS n FROM posts").fetchone()["n"] == 5
    # 출시 모드는 V11 의미 대조 비용이 기록된다
    assert conn.execute("SELECT count(*) AS n FROM llm_calls WHERE purpose = 'verify'").fetchone()["n"] == 5


def test_regeneration_once_then_publish(conn, s, now):
    def mutate(kind, draft, attempt):
        if attempt == 1 and "누리전자" in draft["title"]:
            draft["body_md"] += " 이를 두고 논란이 일고 있다."
        return draft

    events, emb, llm = full_day(conn, s, now, mutate=mutate)
    nuri = conn.execute("SELECT * FROM posts WHERE title LIKE '누리전자%'").fetchone()
    assert nuri["meta"]["attempt"] == 2
    retry_call = next(c for c in llm.calls if len(c["messages"]) == 3)
    assert "V8" in retry_call["messages"][2]["content"]  # 실패한 규칙과 문장을 붙여 다시 지시
    assert float(nuri["cost_usd"]) > float(cost_usd("claude-sonnet-5", Usage(7000, 1200)))  # 두 번의 호출 비용 합


def test_fails_twice_cluster_skipped(conn, s, now):
    def mutate(kind, draft, attempt):
        if "전고체" in draft["title"]:
            draft["body_md"] = draft["body_md"].replace("1000번", "2000번")
        return draft

    full_day(conn, s, now, mutate=mutate)
    assert conn.execute("SELECT count(*) AS n FROM posts WHERE title LIKE '%전고체%'").fetchone()["n"] == 0
    log = conn.execute("SELECT payload FROM decision_log WHERE kind='verify' AND payload->>'outcome'='skipped'").fetchone()
    assert "V3" in log["payload"]["failed_rules"]
    assert conn.execute("SELECT count(*) AS n FROM clusters WHERE state='skipped'").fetchone()["n"] == 1


def test_json_parse_failure_is_v1(conn, s, now):
    events, emb, _ = setup_day(conn, s, now)

    class Broken(FakeLLM):
        def create(self, params):
            r = super().create(params)
            r.text = "죄송하지만 " + r.text[:50]
            return r

    llm = Broken(events)
    from worker.process.select import select_targets

    select_targets(conn, now, s)
    batch.submit_pending(conn, llm, s, now)
    process_received(conn, s, emb, llm, now)
    reports = conn.execute("SELECT verify_report FROM generation_requests WHERE attempt = 1").fetchall()
    assert all(r["verify_report"]["rules"][0]["id"] == "V1" and not r["verify_report"]["rules"][0]["ok"] for r in reports)


def test_review_reject_and_approve(conn, s, now):
    events, emb, _ = setup_day(conn, s, now)
    s["review"]["enabled"] = True
    llm = FakeLLM(events)
    from worker.process.select import select_targets

    select_targets(conn, now, s)
    batch.submit_pending(conn, llm, s, now)
    process_received(conn, s, emb, llm, now)
    ids = [r["id"] for r in conn.execute("SELECT id FROM drafts ORDER BY id").fetchall()]
    reject_draft(conn, ids[0], "fact_error", "숫자 확인 필요", now)
    seq = publish_draft(conn, s, emb, ids[1], now, "approved")
    assert seq is not None
    statuses = {r["id"]: r["status"] for r in conn.execute("SELECT id, status FROM drafts").fetchall()}
    assert statuses[ids[0]] == "rejected" and statuses[ids[1]] == "approved"
    assert conn.execute("SELECT count(*) AS n FROM posts").fetchone()["n"] == 1
    assert conn.execute("SELECT * FROM v_review_weekly").fetchone()["rejected"] == 1


def test_batch_mode_and_timeout(conn, s, now):
    events, emb, _ = setup_day(conn, s, now)
    s["select"]["immediate_top"] = 0
    s["select"]["breaking_outlets"] = 99

    class Slow(FakeLLM):
        def batch_status(self, batch_id):
            return "in_progress"

    llm = Slow(events)
    from worker.process.select import select_targets

    select_targets(conn, now, s)
    out = batch.submit_pending(conn, llm, s, now)
    assert out["batched"] == 5 and out["immediate"] == 0
    assert batch.collect_batches(conn, llm, s, now + timedelta(hours=2))["timed_out"] == 0
    assert batch.collect_batches(conn, llm, s, now + timedelta(hours=25))["timed_out"] == 1
    # 24시간 안에 안 끝나면 즉시 호출로 재제출
    assert {r["mode"] for r in conn.execute("SELECT mode FROM generation_requests").fetchall()} == {"immediate"}
    assert batch.submit_pending(conn, llm, s, now + timedelta(hours=25))["immediate"] == 5


def test_budget_breaker_holds_queue(conn, s, now):
    events, emb, _ = setup_day(conn, s, now)
    conn.execute("INSERT INTO llm_calls (purpose, model, input_tokens, output_tokens, cost_usd) VALUES ('x','m',1,1,30)")
    conn.commit()
    from worker.process.select import select_targets

    select_targets(conn, now, s)
    out = batch.submit_pending(conn, FakeLLM(events), s, now)
    assert out["held"] == 5 and out["immediate"] == 0
    assert conn.execute("SELECT count(*) AS n FROM generation_requests WHERE status='pending'").fetchone()["n"] == 5


def test_links_and_terms(conn, s, now):
    full_day(conn, s, now)
    # 두 번째 날: 같은 사건 후속 기사 → 같은 slug, follows 링크
    rows = conn.execute("SELECT slug FROM slugs ORDER BY slug").fetchall()
    assert {r["slug"] for r in rows} >= {"누리전자-실적", "내년도-예산안", "한빛시-물류창고-화재"}
    terms = conn.execute("SELECT count(*) AS n FROM term_mentions").fetchone()["n"]
    assert terms >= 5
