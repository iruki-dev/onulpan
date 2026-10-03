-- 0003: 권한과 대시보드용 SQL 뷰
-- 모든 지표는 이미 있는 테이블에 대한 뷰로 만든다. 별도 분석 도구를 두지 않는다.

-- ── 권한 ───────────────────────────────────────────────
GRANT USAGE ON SCHEMA public TO app_writer, app_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO app_writer, app_reader;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_writer, app_reader;

-- 워커: 작업 테이블은 전부, 추가 전용 테이블은 SELECT·INSERT만
GRANT INSERT, UPDATE, DELETE ON
  outlets, raw_articles, clusters, slugs, slug_aliases, term_mentions, jobs, llm_calls,
  generation_requests, llm_batches, drafts, email_sends, email_suppressions, login_tokens,
  events, events_monthly, alerts_sent, users, user_prefs, reading_cursors, error_reports, payments
TO app_writer;
GRANT INSERT ON posts, post_links, post_sources, editions, decision_log, front_pages TO app_writer;

-- 웹: 읽기 + 사용자 상태와 작업 요청
GRANT INSERT, UPDATE ON users, user_prefs, reading_cursors, invites, login_tokens, payments,
  email_suppressions, error_reports TO app_reader;
GRANT DELETE ON user_prefs, reading_cursors, login_tokens TO app_reader;
GRANT INSERT ON events, jobs TO app_reader;
GRANT UPDATE ON drafts, outlets TO app_reader;       -- 관리 화면(창업자 전용): 승인·반려, 매체 제외
GRANT UPDATE (email_enabled) ON user_prefs TO app_reader;

REVOKE UPDATE, DELETE, TRUNCATE ON posts, post_links, post_sources, editions, decision_log, front_pages
  FROM app_writer, app_reader;

-- ── 뷰 ────────────────────────────────────────────────
-- KST 날짜 헬퍼
CREATE OR REPLACE FUNCTION kst_date(ts timestamptz) RETURNS date
  LANGUAGE sql IMMUTABLE AS $$ SELECT (ts AT TIME ZONE 'Asia/Seoul')::date $$;

-- 규칙별 검증 실패율 (V1~V11, 일별)
CREATE OR REPLACE VIEW v_verify_rule_daily AS
SELECT kst_date(g.finished_at) AS day,
       r->>'id'               AS rule_id,
       count(*)               AS checked,
       count(*) FILTER (WHERE (r->>'ok')::boolean = false) AS failed,
       round(100.0 * count(*) FILTER (WHERE (r->>'ok')::boolean = false) / NULLIF(count(*),0), 1) AS fail_pct
FROM generation_requests g
CROSS JOIN LATERAL jsonb_array_elements(COALESCE(g.verify_report->'rules', '[]'::jsonb)) r
WHERE g.verify_report IS NOT NULL AND g.finished_at IS NOT NULL
GROUP BY 1, 2;

-- 검증 통과율(첫 생성에서 모든 규칙 통과)과 폐기율(재생성 후에도 실패해 skipped)
CREATE OR REPLACE VIEW v_quality_daily AS
WITH first AS (
  SELECT kst_date(created_at) AS day,
         count(*) FILTER (WHERE status NOT IN ('pending','submitted','expired')) AS generated,
         count(*) FILTER (WHERE (verify_report->>'passed')::boolean) AS passed_first
  FROM generation_requests WHERE attempt = 1 GROUP BY 1
), selected AS (
  SELECT kst_date(created_at) AS day,
         count(*) AS selected_clusters
  FROM generation_requests WHERE attempt = 1 AND kind = 'fact' GROUP BY 1
), skipped AS (
  SELECT kst_date(at) AS day, count(*) AS skipped_clusters
  FROM decision_log WHERE kind = 'verify' AND payload->>'outcome' = 'skipped' GROUP BY 1
)
SELECT f.day, f.generated, f.passed_first,
       round(100.0 * f.passed_first / NULLIF(f.generated,0), 1) AS pass_pct,
       COALESCE(s.selected_clusters,0) AS selected_clusters,
       COALESCE(k.skipped_clusters,0)  AS skipped_clusters,
       round(100.0 * COALESCE(k.skipped_clusters,0) / NULLIF(s.selected_clusters,0), 1) AS discard_pct
FROM first f LEFT JOIN selected s USING (day) LEFT JOIN skipped k USING (day);

-- LLM 비용
CREATE OR REPLACE VIEW v_llm_cost_daily AS
SELECT kst_date(at) AS day, purpose, model,
       count(*) AS calls, sum(input_tokens) AS input_tokens, sum(output_tokens) AS output_tokens,
       sum(cost_usd) AS cost_usd
FROM llm_calls GROUP BY 1, 2, 3;

CREATE OR REPLACE VIEW v_llm_cost_month AS
SELECT date_trunc('month', at AT TIME ZONE 'Asia/Seoul')::date AS month, sum(cost_usd) AS cost_usd
FROM llm_calls GROUP BY 1;

-- 글당 비용
CREATE OR REPLACE VIEW v_cost_per_post_month AS
SELECT m.month, m.cost_usd,
       (SELECT count(*) FROM posts p WHERE date_trunc('month', p.created_at AT TIME ZONE 'Asia/Seoul')::date = m.month) AS posts,
       round(m.cost_usd / NULLIF((SELECT count(*) FROM posts p WHERE date_trunc('month', p.created_at AT TIME ZONE 'Asia/Seoul')::date = m.month),0), 4) AS cost_per_post
FROM v_llm_cost_month m;

-- 매체별 24시간 수집 건수 (0건 매체 강조용)
CREATE OR REPLACE VIEW v_outlet_collection_24h AS
SELECT o.id, o.name, o.grp, o.active, o.excluded_at,
       count(r.id) AS n_24h, max(r.fetched_at) AS last_fetched
FROM outlets o
LEFT JOIN raw_articles r ON r.outlet_id = o.id AND r.fetched_at > now() - interval '24 hours'
GROUP BY o.id;

-- 사람 반려율 (베타, 주별)
CREATE OR REPLACE VIEW v_review_weekly AS
SELECT date_trunc('week', decided_at AT TIME ZONE 'Asia/Seoul')::date AS week,
       count(*) FILTER (WHERE status IN ('approved','rejected')) AS reviewed,
       count(*) FILTER (WHERE status = 'rejected') AS rejected,
       count(*) FILTER (WHERE status = 'auto') AS auto_published,
       round(100.0 * count(*) FILTER (WHERE status = 'rejected')
             / NULLIF(count(*) FILTER (WHERE status IN ('approved','rejected')),0), 2) AS reject_pct
FROM drafts WHERE decided_at IS NOT NULL GROUP BY 1;

-- 정정률 (월별)
CREATE OR REPLACE VIEW v_correction_monthly AS
SELECT date_trunc('month', created_at AT TIME ZONE 'Asia/Seoul')::date AS month,
       count(*) AS posts,
       count(*) FILTER (WHERE kind = 'correction') AS corrections,
       round(100.0 * count(*) FILTER (WHERE kind = 'correction') / NULLIF(count(*),0), 2) AS correction_pct
FROM posts GROUP BY 1;

-- 독자 지표 (일별): 조간 연 사람, 완독, 링크 클릭
CREATE OR REPLACE VIEW v_reader_daily AS
SELECT kst_date(at) AS day,
       count(DISTINCT COALESCE(user_id::text, anon_id)) FILTER (WHERE name = 'edition_open')     AS openers,
       count(DISTINCT COALESCE(user_id::text, anon_id)) FILTER (WHERE name = 'edition_complete') AS completers,
       count(*) FILTER (WHERE name = 'link_click') AS link_clicks,
       count(*) FILTER (WHERE name = 'audio_interest') AS audio_interest
FROM events GROUP BY 1;

-- 신규 가입 (초대 코드·채널별)
CREATE OR REPLACE VIEW v_signups_daily AS
SELECT kst_date(u.created_at) AS day, COALESCE(i.channel, CASE WHEN u.invite_code IS NULL THEN 'direct' ELSE 'unknown' END) AS channel,
       u.invite_code, count(*) AS signups
FROM users u LEFT JOIN invites i ON i.code = u.invite_code
WHERE u.deleted_at IS NULL
GROUP BY 1, 2, 3;

-- 1면 공정성 점검 (월별 섹션 분포)
CREATE OR REPLACE VIEW v_front_section_monthly AS
SELECT date_trunc('month', f.edition_date)::date AS month, p.section, count(*) AS n,
       round(100.0 * count(*) / sum(count(*)) OVER (PARTITION BY date_trunc('month', f.edition_date)::date), 1) AS pct
FROM (SELECT DISTINCT ON (edition_date) * FROM front_pages ORDER BY edition_date, id DESC) f
CROSS JOIN LATERAL unnest(f.seqs) s(seq)
JOIN posts p ON p.seq = s.seq
GROUP BY 1, 2;

-- 1면 매체군 분포 (월별)
CREATE OR REPLACE VIEW v_front_group_monthly AS
SELECT date_trunc('month', f.edition_date)::date AS month, o.grp, count(*) AS n
FROM (SELECT DISTINCT ON (edition_date) * FROM front_pages ORDER BY edition_date, id DESC) f
CROSS JOIN LATERAL unnest(f.seqs) s(seq)
JOIN post_sources ps ON ps.post_seq = s.seq
JOIN outlets o ON o.id = ps.outlet_id
GROUP BY 1, 2;

GRANT SELECT ON ALL TABLES IN SCHEMA public TO app_writer, app_reader;
