-- 0006: 뉴스 이미지. 기준 문서는 ‘뉴스 이미지 사용 가이드’ (docs/images.md)
-- 이용 조건이 확인된 출처의 이미지만 쓰고, 출처가 지정한 크레딧을 이미지 바로 아래에 표기한다.
-- 글(posts)은 추가 전용이지만 이미지는 권리자 요청으로 언제든 내릴 수 있어야 하므로 별도 테이블로 둔다.

-- 출처 등록부: rules/image_sources.yaml에서 동기화한다 (편집 원칙 페이지의 공개 목록도 여기서 나온다)
CREATE TYPE image_tier AS ENUM ('free','press','own');   -- 자유 이용 | 보도용 제공 | 자체 제작
CREATE TABLE image_sources (
  key           text PRIMARY KEY,
  name          text NOT NULL,
  tier          image_tier NOT NULL,
  url           text,
  examples      text NOT NULL DEFAULT '',  -- 주요 이미지
  conditions    text NOT NULL,             -- 사용 조건 (공개 문구)
  licenses      text[] NOT NULL,           -- 허용 라이선스 코드
  scope_required boolean NOT NULL DEFAULT false,  -- 보도용: 해당 소식을 다루는 글에서만
  auto          boolean NOT NULL DEFAULT false,   -- 워커가 자동으로 검색하는 출처
  ord           int NOT NULL DEFAULT 0,
  active        boolean NOT NULL DEFAULT true
);

CREATE TABLE images (
  id            bigserial PRIMARY KEY,
  source_key    text NOT NULL REFERENCES image_sources(key),
  origin_url    text NOT NULL,             -- 원본 페이지(이용 조건이 적힌 곳)
  file_url      text,                      -- 원본 파일 주소
  hotlink       boolean NOT NULL DEFAULT false,  -- 출처 약관상 원본 주소로 불러와야 하는 경우 (Unsplash)
  stored_path   text,                      -- IMAGE_DIR 기준 표시용 파일 (가로·세로 비율 유지, 자르지 않음)
  original_path text,                      -- 내려받은 원본 그대로
  sha256        text,
  mime          text,
  width         int,
  height        int,
  title         text,
  alt           text NOT NULL,             -- 대체 텍스트
  author        text,
  license       text NOT NULL,             -- rules/image_sources.yaml licenses 코드
  license_url   text,
  credit        text NOT NULL,             -- 지정 크레딧. 이미지 바로 아래에 이 문구 그대로
  usage_terms   text,                      -- 개별 이미지의 이용 조건 원문 요약
  modifiable    boolean NOT NULL DEFAULT false,  -- 변경 허용 라이선스일 때만 자르기·덧씌우기
  subject       text,                      -- person | place | object | event | concept | data
  scope_slug    text REFERENCES slugs(slug),     -- 보도용: 이 소식(slug)을 다루는 글에서만
  query         text,                      -- 자동 검색에 쓴 말
  checklist     jsonb NOT NULL DEFAULT '{}',     -- 사용 전 체크리스트 4항목 결과와 근거
  status        text NOT NULL DEFAULT 'pending'
                CHECK (status IN ('fetching','pending','active','rejected','taken_down','failed')),
  found_by      text NOT NULL CHECK (found_by IN ('auto','admin','graphic')),
  note          text,
  created_at    timestamptz NOT NULL DEFAULT now(),
  reviewed_at   timestamptz,
  taken_down_at timestamptz
);
CREATE UNIQUE INDEX images_source_file ON images (source_key, file_url) WHERE file_url IS NOT NULL;
CREATE INDEX ON images (status, created_at DESC);
CREATE INDEX ON images (scope_slug) WHERE scope_slug IS NOT NULL;

-- 글과 이미지의 연결. 글은 바뀌지 않아도 연결은 내리거나 바꿀 수 있다.
CREATE TABLE post_images (
  id            bigserial PRIMARY KEY,
  post_seq      bigint NOT NULL REFERENCES posts(seq),
  image_id      bigint NOT NULL REFERENCES images(id),
  role          text NOT NULL DEFAULT 'lead' CHECK (role IN ('lead')),
  caption       text,
  status        text NOT NULL DEFAULT 'active' CHECK (status IN ('active','removed')),
  created_at    timestamptz NOT NULL DEFAULT now(),
  removed_at    timestamptz,
  removed_reason text
);
CREATE UNIQUE INDEX post_images_one_lead ON post_images (post_seq, role) WHERE status = 'active';
CREATE INDEX ON post_images (image_id);

-- 이미지 검색 시도 (같은 글을 매번 다시 찾지 않도록)
CREATE TABLE image_searches (
  post_seq      bigint PRIMARY KEY REFERENCES posts(seq),
  attempts      int NOT NULL DEFAULT 0,
  last_at       timestamptz NOT NULL DEFAULT now(),
  outcome       text NOT NULL,             -- attached | none | error
  brief         jsonb
);

-- 권리자 요청: 받으면 바로 내리고 회신한다
CREATE TABLE image_requests (
  id            bigserial PRIMARY KEY,
  image_id      bigint NOT NULL REFERENCES images(id),
  name          text NOT NULL,
  email         text NOT NULL,
  relation      text NOT NULL CHECK (relation IN ('owner','agent','portrait','other')),
  body          text NOT NULL,
  status        text NOT NULL DEFAULT 'open' CHECK (status IN ('open','restored','replaced','removed')),
  resolution    text,                      -- 회신 내용 (이용 근거 또는 조치)
  replacement_image_id bigint REFERENCES images(id),
  received_at   timestamptz NOT NULL DEFAULT now(),
  acked_at      timestamptz,               -- 접수 회신
  resolved_at   timestamptz
);
CREATE INDEX ON image_requests (status, received_at);

-- ── 권한 ──
GRANT INSERT, UPDATE, DELETE ON image_sources, images, post_images, image_searches, image_requests TO app_writer;
-- 웹: 권리자 요청 접수와 즉시 내리기, 관리 화면(창업자 전용)의 승인·등록·교체
GRANT INSERT, UPDATE ON images, post_images, image_requests TO app_reader;
