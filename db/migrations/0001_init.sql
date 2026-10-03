-- 0001: 기술 설계서 ‘데이터 모델’ 절 전체
-- 추가 전용 테이블(posts, post_links, post_sources, editions, decision_log)은 권한 + 트리거로 이중 강제한다.

-- 확장
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 역할: 워커는 app_writer, 웹은 app_reader. 로그인 역할은 infra/bootstrap.sh가 만들고 여기에 넣는다.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_writer') THEN CREATE ROLE app_writer NOLOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_reader') THEN CREATE ROLE app_reader NOLOGIN; END IF;
END $$;

-- ① 매체: 성향으로 분류하지 않는다. 매체군(형태)만 둔다.
CREATE TYPE outlet_group AS ENUM ('national_daily','broadcast','wire','economic','regional','online','public');
CREATE TABLE outlets (
  id            serial PRIMARY KEY,
  name          text NOT NULL,
  domain        text NOT NULL UNIQUE,
  feed_url      text,
  feed_type     text NOT NULL CHECK (feed_type IN ('rss','api')),
  grp           outlet_group NOT NULL,
  active        boolean NOT NULL DEFAULT true,
  excluded_at   timestamptz,          -- 매체 요청으로 제외한 시각
  excluded_note text
);

-- ② 원문: 본문은 30일 뒤 NULL로 비운다
CREATE TABLE raw_articles (
  id            bigserial PRIMARY KEY,
  outlet_id     int NOT NULL REFERENCES outlets(id),
  url           text NOT NULL UNIQUE,
  title         text NOT NULL,
  body          text,
  published_at  timestamptz NOT NULL,
  fetched_at    timestamptz NOT NULL DEFAULT now(),
  simhash       bigint NOT NULL,
  embedding     vector(1024),          -- bge-m3 dense
  cluster_id    bigint,
  duplicate_of  bigint REFERENCES raw_articles(id),
  body_purged_at timestamptz
);
CREATE INDEX ON raw_articles (published_at DESC);
CREATE INDEX ON raw_articles (cluster_id);
CREATE INDEX ON raw_articles USING hnsw (embedding vector_cosine_ops);

-- ③ 묶음: 같은 사건을 다룬 기사들 (작업용, 수정 가능)
CREATE TABLE clusters (
  id            bigserial PRIMARY KEY,
  centroid      vector(1024) NOT NULL,
  first_seen    timestamptz NOT NULL,
  last_seen     timestamptz NOT NULL,
  n_articles    int NOT NULL DEFAULT 0,
  n_outlets     int NOT NULL DEFAULT 0,
  n_groups      int NOT NULL DEFAULT 0,  -- 서로 다른 매체군 수
  slug          text,                    -- 연결된 주제 이름표
  state         text NOT NULL DEFAULT 'open' CHECK (state IN ('open','written','closed','skipped'))
);
CREATE INDEX ON clusters USING hnsw (centroid vector_cosine_ops);
ALTER TABLE raw_articles ADD CONSTRAINT raw_articles_cluster_fk FOREIGN KEY (cluster_id) REFERENCES clusters(id);

-- ④ 글 저장소: 추가 전용
CREATE TYPE post_kind AS ENUM ('fact','synthesis','issue','explainer','culture','correction');
CREATE TYPE section AS ENUM ('politics','economy','society','world','scitech','culture','none');
CREATE TABLE slugs (
  slug          text PRIMARY KEY,        -- 예: 반도체-수출규제
  display_name  text NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE slug_aliases (
  alias         text PRIMARY KEY,        -- 본문 속 표기 → slug
  slug          text NOT NULL REFERENCES slugs(slug)
);
CREATE TABLE posts (
  seq           bigserial PRIMARY KEY,   -- 읽기 커서가 가리키는 단조 증가 번호
  id            uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
  kind          post_kind NOT NULL,
  section       section NOT NULL,
  slug          text REFERENCES slugs(slug),
  cluster_id    bigint REFERENCES clusters(id),
  title         text NOT NULL,
  summary       text NOT NULL,
  body_md       text NOT NULL,
  char_count    int NOT NULL,
  meta          jsonb NOT NULL DEFAULT '{}',   -- 종류별 자유 필드
  importance    real NOT NULL DEFAULT 0,       -- 발행 시점 점수 (편집기 입력)
  model         text NOT NULL,
  prompt_version text NOT NULL,
  verify_report jsonb NOT NULL,
  cost_usd      numeric(8,5) NOT NULL,
  embedding     vector(1024),
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON posts (slug, seq DESC);          -- slug의 최신 글 찾기
CREATE INDEX ON posts (created_at DESC);
CREATE INDEX ON posts USING hnsw (embedding vector_cosine_ops);

CREATE TYPE link_rel AS ENUM ('refers','follows','corrects','explains','summarizes');
CREATE TABLE post_links (
  from_seq      bigint NOT NULL REFERENCES posts(seq),
  to_seq        bigint NOT NULL REFERENCES posts(seq),
  rel           link_rel NOT NULL,
  anchor_text   text,                    -- 본문에서 링크가 걸린 표기
  PRIMARY KEY (from_seq, to_seq, rel),
  CHECK (from_seq > to_seq)              -- 새 글은 과거 글만 가리킨다
);
CREATE INDEX ON post_links (to_seq);     -- 역참조(정정·후속 표시)

CREATE TABLE post_sources (
  post_seq      bigint NOT NULL REFERENCES posts(seq),
  raw_article_id bigint NOT NULL REFERENCES raw_articles(id),
  outlet_id     int NOT NULL REFERENCES outlets(id),
  url           text NOT NULL,           -- 원문 본문이 지워져도 남는다
  title         text NOT NULL,
  PRIMARY KEY (post_seq, raw_article_id)
);

-- 추가 전용 강제: 권한 + 트리거
CREATE OR REPLACE FUNCTION forbid_mutation() RETURNS trigger AS $$
BEGIN RAISE EXCEPTION '% is append-only', TG_TABLE_NAME; END; $$ LANGUAGE plpgsql;
CREATE TRIGGER posts_append_only BEFORE UPDATE OR DELETE ON posts
  FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
CREATE TRIGGER links_append_only BEFORE UPDATE OR DELETE ON post_links
  FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
CREATE TRIGGER sources_append_only BEFORE UPDATE OR DELETE ON post_sources
  FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
-- TRUNCATE는 행 트리거를 거치지 않으므로 문장 트리거로 막는다
CREATE TRIGGER posts_no_truncate BEFORE TRUNCATE ON posts
  FOR EACH STATEMENT EXECUTE FUNCTION forbid_mutation();
CREATE TRIGGER links_no_truncate BEFORE TRUNCATE ON post_links
  FOR EACH STATEMENT EXECUTE FUNCTION forbid_mutation();
CREATE TRIGGER sources_no_truncate BEFORE TRUNCATE ON post_sources
  FOR EACH STATEMENT EXECUTE FUNCTION forbid_mutation();
REVOKE UPDATE, DELETE, TRUNCATE ON posts, post_links, post_sources FROM app_writer, app_reader;

-- ⑤ 해설 후보: 본문에 등장했지만 해설 글이 없는 용어
CREATE TABLE term_mentions (
  term          text NOT NULL,
  post_seq      bigint NOT NULL REFERENCES posts(seq),
  PRIMARY KEY (term, post_seq)
);

-- ⑥ 사용자
CREATE TABLE users (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email         text NOT NULL UNIQUE,
  provider      text NOT NULL,           -- google | kakao | email
  plan          text NOT NULL DEFAULT 'free' CHECK (plan IN ('free','founding','premium')),
  invite_code   text,                    -- 가입 경로 추적 (CAC 측정)
  utm           jsonb,
  marketing_opt_in boolean NOT NULL DEFAULT false,
  created_at    timestamptz NOT NULL DEFAULT now(),
  deleted_at    timestamptz
);
CREATE TABLE user_prefs (
  user_id       uuid PRIMARY KEY REFERENCES users(id),
  preset        text NOT NULL DEFAULT 'standard' CHECK (preset IN ('short','standard','long')),
  section_weights jsonb NOT NULL DEFAULT '{}',   -- {"economy": 1.3, "politics": 0.7}
  niche_topics  text[] NOT NULL DEFAULT '{}',    -- 유료: slug 목록 최대 5
  delivery_hour smallint NOT NULL DEFAULT 7 CHECK (delivery_hour BETWEEN 7 AND 10), -- KST
  email_enabled boolean NOT NULL DEFAULT true,
  CHECK (cardinality(niche_topics) <= 5)
);
CREATE TABLE reading_cursors (
  user_id       uuid PRIMARY KEY REFERENCES users(id),
  last_seq      bigint NOT NULL,         -- 마지막으로 연 조간의 as_of_seq
  updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE invites (
  code          text PRIMARY KEY,
  owner_id      uuid REFERENCES users(id),     -- NULL이면 채널 코드 (예: evertime-w1)
  channel       text NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT now()
);

-- ⑦ 발행 기록: 누가 어떤 지면을 받았는지 (추가 전용)
CREATE TABLE editions (
  id            bigserial PRIMARY KEY,
  user_id       uuid NOT NULL REFERENCES users(id),
  edition_date  date NOT NULL,
  as_of_seq     bigint NOT NULL,
  preset        text NOT NULL,
  slots         jsonb NOT NULL,          -- [{slot:"front", seq:1234}, …] 순서 보존
  editor_version text NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT now()
);
-- 설정 변경으로 같은 날 재조립하면 새 행을 넣는다. 조회는 (user_id, edition_date)의 최신 id
CREATE INDEX ON editions (user_id, edition_date, id DESC);
CREATE TRIGGER editions_append_only BEFORE UPDATE OR DELETE ON editions
  FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
CREATE TRIGGER editions_no_truncate BEFORE TRUNCATE ON editions
  FOR EACH STATEMENT EXECUTE FUNCTION forbid_mutation();

-- ⑧ 판단 기록과 행동 로그
CREATE TABLE decision_log (
  id            bigserial PRIMARY KEY,
  kind          text NOT NULL,           -- assign | select | verify | explainer_trigger
  ref           text NOT NULL,
  payload       jsonb NOT NULL,
  at            timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON decision_log (kind, at DESC);
CREATE INDEX ON decision_log (ref);
CREATE TRIGGER decisions_append_only BEFORE UPDATE OR DELETE ON decision_log
  FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
CREATE TRIGGER decisions_no_truncate BEFORE TRUNCATE ON decision_log
  FOR EACH STATEMENT EXECUTE FUNCTION forbid_mutation();
REVOKE UPDATE, DELETE, TRUNCATE ON editions, decision_log FROM app_writer, app_reader;

CREATE TABLE events (
  id            bigserial PRIMARY KEY,
  user_id       uuid,
  anon_id       text,
  name          text NOT NULL,           -- 이벤트 목록은 PRD 참조
  props         jsonb NOT NULL DEFAULT '{}',
  at            timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON events (name, at);

-- ⑨ 작업 큐와 비용 기록
CREATE TABLE jobs (
  id            bigserial PRIMARY KEY,
  type          text NOT NULL,
  payload       jsonb NOT NULL,
  status        text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','done','failed')),
  run_after     timestamptz NOT NULL DEFAULT now(),
  attempts      int NOT NULL DEFAULT 0,
  last_error    text
);
CREATE INDEX ON jobs (status, run_after);
CREATE TABLE llm_calls (
  id            bigserial PRIMARY KEY,
  purpose       text NOT NULL,           -- generate_fact | generate_issue | verify | …
  model         text NOT NULL,
  batch_id      text,
  input_tokens  int NOT NULL,
  output_tokens int NOT NULL,
  cost_usd      numeric(8,5) NOT NULL,
  at            timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON llm_calls (at);
