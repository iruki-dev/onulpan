-- 0002: 파이프라인 운영에 필요한 작업용 테이블 (설계서 본문에서 언급된 drafts, payments, 1면 캐시, 발송 등)

-- 처리 보조 컬럼: 회색 구간 판정에 쓰는 고유명사, 묶음이 글이 된 시각
ALTER TABLE raw_articles ADD COLUMN nnps text[] NOT NULL DEFAULT '{}';
ALTER TABLE raw_articles ADD COLUMN lead text;            -- 제목+리드(임베딩 입력). 본문과 같이 30일 뒤 비운다
CREATE INDEX ON raw_articles (outlet_id, fetched_at DESC);
ALTER TABLE clusters ADD COLUMN written_at timestamptz;
CREATE INDEX ON clusters (state, last_seen DESC);
CREATE INDEX ON posts (kind, created_at DESC);
CREATE INDEX ON posts (cluster_id);
CREATE INDEX ON term_mentions (post_seq);

-- 생성 요청: 5단계(생성) → 6단계(검증)의 상태를 추적한다. 재생성은 parent_id로 잇는다.
CREATE TABLE generation_requests (
  id            bigserial PRIMARY KEY,
  kind          post_kind NOT NULL,
  cluster_id    bigint REFERENCES clusters(id),
  slug          text,
  term          text,
  topic         jsonb,                   -- 교양: 편집 캘린더 항목
  attempt       smallint NOT NULL DEFAULT 1 CHECK (attempt IN (1,2)),
  parent_id     bigint REFERENCES generation_requests(id),
  priority      real NOT NULL DEFAULT 0, -- 중요도. 예산 복구 시 이 순서로 처리
  mode          text NOT NULL DEFAULT 'batch' CHECK (mode IN ('batch','immediate')),
  status        text NOT NULL DEFAULT 'pending' CHECK (status IN
                  ('pending','submitted','received','retry','failed','discarded','expired','drafted','published','rejected')),
  input         jsonb,                   -- 프롬프트에 넣은 문서 id·관련 글 seq
  feedback      jsonb,                   -- 재생성 시 실패 규칙과 문장
  model         text,
  prompt_version text,
  batch_id      text,
  custom_id     text UNIQUE,
  response      jsonb,                   -- 파싱한 생성 JSON (실패 시 raw 텍스트)
  verify_report jsonb,
  input_tokens  int NOT NULL DEFAULT 0,
  output_tokens int NOT NULL DEFAULT 0,
  cost_usd      numeric(8,5) NOT NULL DEFAULT 0,
  created_at    timestamptz NOT NULL DEFAULT now(),
  submitted_at  timestamptz,
  finished_at   timestamptz
);
CREATE INDEX ON generation_requests (status, priority DESC);
CREATE INDEX ON generation_requests (kind, created_at);
CREATE INDEX ON generation_requests (batch_id);

CREATE TABLE llm_batches (
  batch_id      text PRIMARY KEY,
  status        text NOT NULL DEFAULT 'in_progress' CHECK (status IN ('in_progress','ended','canceled','collected')),
  n_requests    int NOT NULL,
  submitted_at  timestamptz NOT NULL DEFAULT now(),
  collected_at  timestamptz
);

-- 베타 전용: 게시 전 대기 (수정·삭제 가능한 작업 테이블)
CREATE TABLE drafts (
  id            bigserial PRIMARY KEY,
  cluster_id    bigint REFERENCES clusters(id),
  request_id    bigint REFERENCES generation_requests(id),
  kind          post_kind NOT NULL,
  payload       jsonb NOT NULL,          -- 생성 JSON 전체
  verify_report jsonb NOT NULL,
  status        text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected','auto')),
  reject_reason text CHECK (reject_reason IS NULL OR reject_reason IN ('fact_error','interpretation_error','expression','duplicate')),
  reject_note   text,
  post_seq      bigint REFERENCES posts(seq),
  created_at    timestamptz NOT NULL DEFAULT now(),
  decided_at    timestamptz
);
CREATE INDEX ON drafts (status, created_at);

-- 1면: 하루 한 번 계산해 모든 사용자가 공유한다 (추가 전용. 같은 날 다시 계산하면 새 행)
CREATE TABLE front_pages (
  id            bigserial PRIMARY KEY,
  edition_date  date NOT NULL,
  seqs          bigint[] NOT NULL,
  fallback      boolean NOT NULL DEFAULT false,  -- 후보 3편 미만이라 전날 1면의 종합 글로 채움
  issue_seq     bigint REFERENCES posts(seq),    -- 오늘의 쟁점 정리 (전 사용자 공통)
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON front_pages (edition_date, id DESC);
CREATE TRIGGER front_pages_append_only BEFORE UPDATE OR DELETE ON front_pages
  FOR EACH ROW EXECUTE FUNCTION forbid_mutation();

-- 이메일 발송: 조립이 끝난 editions만 보낸다
CREATE TABLE email_sends (
  id            bigserial PRIMARY KEY,
  edition_id    bigint NOT NULL REFERENCES editions(id),
  user_id       uuid NOT NULL REFERENCES users(id),
  edition_date  date NOT NULL,
  scheduled_hour smallint NOT NULL,
  status        text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','sent','failed','suppressed')),
  attempts      int NOT NULL DEFAULT 0,
  message_id    text,
  last_error    text,
  next_attempt_at timestamptz,
  sent_at       timestamptz,
  UNIQUE (user_id, edition_date)
);
CREATE INDEX ON email_sends (status, edition_date, scheduled_hour);
CREATE TABLE email_suppressions (
  email         text PRIMARY KEY,
  reason        text NOT NULL,           -- bounce | complaint | unsubscribe
  at            timestamptz NOT NULL DEFAULT now()
);

-- 이메일 로그인 링크
CREATE TABLE login_tokens (
  token_hash    text PRIMARY KEY,
  email         text NOT NULL,
  expires_at    timestamptz NOT NULL,
  used_at       timestamptz
);

-- 오류 제보: 48시간 안에 답변
CREATE TABLE error_reports (
  id            bigserial PRIMARY KEY,
  post_seq      bigint REFERENCES posts(seq),
  user_id       uuid REFERENCES users(id),
  contact       text,
  body          text NOT NULL,
  status        text NOT NULL DEFAULT 'open' CHECK (status IN ('open','confirmed','rejected')),
  answer        text,
  correction_seq bigint REFERENCES posts(seq),
  created_at    timestamptz NOT NULL DEFAULT now(),
  answered_at   timestamptz
);

-- 창립 멤버 선결제
CREATE TABLE payments (
  id            bigserial PRIMARY KEY,
  user_id       uuid NOT NULL REFERENCES users(id),
  provider      text NOT NULL,           -- tosspayments
  order_id      text NOT NULL UNIQUE,
  product       text NOT NULL,           -- founding_12m
  amount        int NOT NULL,
  status        text NOT NULL DEFAULT 'ready' CHECK (status IN ('ready','paid','failed','refunded')),
  payment_key   text,
  raw           jsonb,
  created_at    timestamptz NOT NULL DEFAULT now(),
  paid_at       timestamptz,
  refunded_at   timestamptz
);

-- events 13개월 경과분은 월별 집계만 남긴다
CREATE TABLE events_monthly (
  month         date NOT NULL,
  name          text NOT NULL,
  n_events      bigint NOT NULL,
  n_users       bigint NOT NULL,
  PRIMARY KEY (month, name)
);

-- 알림 중복 방지
CREATE TABLE alerts_sent (
  key           text PRIMARY KEY,
  at            timestamptz NOT NULL DEFAULT now()
);

-- 마이그레이션 기록은 러너가 schema_migrations에 남긴다
