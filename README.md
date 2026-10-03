# 오늘판

여러 언론 보도를 AI가 종합해 쓰는 아침 조간. 하루 한 번 쓰고, 여러 번 읽는 **추가 전용 글 저장소**다.
이 저장소는 ‘오늘판 기술 설계서 — 개발 상세 파이프라인’과 ‘오늘판 편집 원칙’을 그대로 구현한 모노레포다.

```
onulpan/
├── worker/            # Python: 수집 → 정규화·중복 제거 → 묶기 → 선정 → 생성 → 검증 → 게시 → 후속 트리거, 편집기, 발송
├── web/               # Next.js 16 (App Router): 조간·글·위키·설정·로그인·관리 화면. 읽기 + 작업 요청만
├── db/migrations/     # 번호 순 SQL. 추가 전용 트리거·권한·대시보드 뷰
├── prompts/           # 버전 붙은 프롬프트 (system.v1, fact.v1, …). 글마다 prompt_version을 기록
├── rules/             # outlets.yaml, banned_phrases.txt, glossary.tsv, relative_dates.txt, culture_calendar.yaml
├── config/            # beta.yaml / launch.yaml — 코드는 같고 설정값만 다르다
├── infra/             # bootstrap.sh, restore.sh, backup.sh, systemd 유닛·타이머(KST)
└── tests/             # pytest + 가상 하루치 픽스처(tests/fixtures/demo_day.yaml)
```

## 일곱 가지 불변식이 코드의 어디에 있나

| 불변식 | 구현 |
| --- | --- |
| 1. 글은 추가만 된다 | `posts`·`post_links`·`post_sources`·`editions`·`decision_log`(+`front_pages`)에 UPDATE/DELETE/TRUNCATE 트리거, 앱 역할에서 권한 회수 (`db/migrations/0001`, `0003`). 정정은 `kind='correction'` 새 글 + `corrects` 링크 |
| 2. 사용자 요청 경로에 LLM 없음 | 웹은 `editions`를 읽기만 한다. 조립은 워커의 `assemble_edition` 하나 (`worker/editor/assemble.py`) |
| 3. 검증 통과 글만 저장소에 | `worker/verify/rules/v01…v11`, `worker/pipeline.py` — 1회 재생성, 또 실패하면 묶음 `skipped` |
| 4. 출처 2곳 이상 + 모델·프롬프트 버전 저장 | V2(매체 2곳, 부족하면 폐기), `post_sources`, `posts.model`·`prompt_version`·`verify_report` |
| 5. 원문 문장 복제 금지 | V7(공통 어절 열 7 이하, 5-gram 15% 미만), 프롬프트 규칙 2 |
| 6. 판단은 로그로 | `decision_log`: assign(묶기), target(선정), verify, select(1면 상위 10과 탈락 사유), publish, review, trigger |
| 7. AI는 필요한 곳에만 | SimHash·임베딩·묶기·선정·숫자 검증은 알고리즘. LLM은 글쓰기(5단계)와 출시 모드의 회색 구간·V11만 |

## 파이프라인 (설계서 ‘파이프라인 단계’ ↔ 코드)

| 단계 | 코드 | 메모 |
| --- | --- | --- |
| 1 수집 | `worker/collect/feeds.py`, `fetch.py`, `robots.py`, `urls.py`, `policy_api.py` | robots.txt, 도메인당 1초 간격, 연락처 UA, 추적 파라미터 제거, 유료·로그인 영역 건너뜀, 정책브리핑 API |
| 2 정규화·중복 제거 | `worker/process/normalize.py`, `simhash.py`, `ingest.py` | kiwipiepy 형태소 3-shingle SimHash, 해밍 3 이하면 `duplicate_of` |
| 3 임베딩·묶기 | `worker/process/embed.py`, `cluster.py` | bge-m3(로컬 CPU). 0.82 합류 / 0.70~0.82 회색 구간(고유명사 2개 공유 + 12시간) / 미만 새 묶음 |
| 4 선정 | `worker/process/select.py`, `importance.py` | 매체 2곳, 24시간, 안정화, 하루 상한, 상위 5·속보성은 즉시 호출 |
| 5 생성 | `worker/generate/prompts.py`, `batch.py`, `gateway.py` | Message Batches(50%), 시스템 프롬프트 캐시, 예산 차단기(80% 알림·100% 중단), 24시간 배치 타임아웃 → 즉시 재제출 |
| 6 검증 | `worker/verify/` | V1~V10 규칙, V11(출시 모드, Haiku 4.5) |
| 7 게시·링크 | `worker/publish/commit.py`, `links.py` | 한 트랜잭션. slug_aliases 사전 매칭으로만 링크 |
| 8 후속 트리거 | `worker/publish/triggers.py` | 종합(3편 또는 7일), 해설(14일·3편, 하루 상한), 쟁점(disputed + 매체군 3), 교양(일요일 7편) |
| 편집기 | `worker/editor/assemble.py`, `front_page.py` | 프리셋 3종, 1면 공통, 40% 상한, 5개 섹션 바닥, novelty, 단신, 오늘의 배경, 교양, 결정성 |
| 발송 | `worker/mail/` | SES(SMTP), 원클릭 수신 거부(RFC 8058), 10분 뒤 1회 재시도 |
| 이미지 | `worker/images/`, `rules/image_sources.yaml` | 기준 `docs/images.md`. 분야별 순서대로 출처 확인 → 사용 전 체크리스트 → 저장(비율 유지 축소본) → 글에 연결. 자체 그래픽(흐름), 권리자 요청 즉시 내림 |

일정(KST)은 `worker/jobs/tasks.py` 머리말과 `infra/systemd/*.timer`에 같은 표로 있다.

## 로컬에서 돌려 보기

필요한 것: Python 3.11+, Node 22, PostgreSQL 16 + pgvector.

```bash
# DB
createdb onulpan
export DATABASE_URL=postgresql://localhost/onulpan ONULPAN_EMBEDDER=hashing ONULPAN_SECRET=dev
pip install -e ".[dev]"
python -m worker.jobs.cli migrate
python -m worker.jobs.cli sync-outlets

# API 키 없이 가상 하루치로 파이프라인 전체를 한 번 돌린다 (가상 매체·가짜 LLM)
python -m worker.jobs.cli seed-demo

# 작업 큐 (설정 변경 재조립, 초안 승인 등)
python -m worker.jobs.cli run-jobs &

# 웹
cd web && npm install
DEV_LOGIN=1 ADMIN_EMAILS=demo@onulpan.local DATABASE_URL_WEB=$DATABASE_URL npm run dev
# http://localhost:3000 → 로그인에서 demo@onulpan.local 입력 (개발 모드는 메일 없이 로그인)
```

실제 수집·생성은 `ANTHROPIC_API_KEY`를 넣고 `python -m worker.jobs.cli collect`, `select`, `collect-batches`를 차례로 돌리거나
`python -m worker.jobs.cli scheduler`(systemd 없이 내부 시계로 KST 일정 실행)를 띄운다. 키가 없으면 선정까지만 하고 대기열에 쌓는다.

## 테스트

```bash
createdb onulpan_test
pytest                      # 워커 98개: 추가 전용 트리거·권한, 규칙별 틀린 초안, 파이프라인 끝에서 끝까지, 편집기, 트리거, 발송
cd web && npm test && npx tsc --noEmit
```

픽스처(`tests/fixtures/demo_day.yaml`)는 가상 매체·기업·인물로 지은 하루치 묶음 6개다(통신 전재 1건, 매체마다 다른 사망자 수, 입장이 갈린 예산안, 한 곳만 보도한 소식).
실제 하루치 묶음 20개로 바꾸는 것은 첫 주 수집이 쌓인 뒤의 일이다(저작권 때문에 원문을 저장소에 넣지 않는다).

## 운영

- **설치·서버 이전(목표 1시간)**: `infra/bootstrap.sh` → `/etc/onulpan.env` 작성(`.env.example`) → `infra/restore.sh` → `systemctl start onulpan.target` → Cloudflare DNS 전환.
- **DB 역할**: 마이그레이션이 `app_writer`(워커)·`app_reader`(웹)를 만들고, bootstrap이 로그인 역할 `onulpan_worker`·`onulpan_web`을 각각에 넣는다. 두 역할 모두 추가 전용 테이블을 고치거나 지울 수 없다.
- **모드 전환**: `ONULPAN_MODE=launch` — 회색 구간 Haiku, V11 의미 대조, 하루 150편, 사람 검토 해제, 예산 $400.
- **편집 규칙 바꾸기**: 금지 표현·용어·매체는 `rules/`에 한 줄 고치고 커밋. 편집기 규칙을 바꾸면 `config/*.yaml`의 `editor.version`을 올린다.
- **관리 화면**: `/admin/today`(초안 검토·파이프라인·규칙별 실패율·비용·독자), `/admin/reports`(제보·정정 글), `/admin/outlets`(언론사 제외 요청), `/admin/invites`, `/admin/images`(이미지 승인·직접 등록·권리자 요청 처리).
- **이미지**: 출처 목록·분야별 순서는 `rules/image_sources.yaml`을 고치고 `sync-image-sources`. 파일은 `IMAGE_DIR`(웹과 워커가 같은 경로)에 쌓이고 R2 백업에 함께 올라간다. 자체 그래픽은 `fonts-noto-cjk`(또는 `IMAGE_FONT`)가 필요하다. 스톡 출처는 `UNSPLASH_ACCESS_KEY`·`PEXELS_API_KEY`·`PIXABAY_API_KEY`가 있을 때만 쓴다.
- **리포트**: 일요일 22:00 주간 품질 리포트(`reports/weekly-*.md`, 묶기 표본 50건 포함), `python -m worker.jobs.cli report-12w`.

## 구현하며 정한 것

- **모델**: 설계서의 ‘Sonnet 5’는 `claude-sonnet-5`, ‘Haiku 4.5’는 `claude-haiku-4-5`. 비용 계산($2/$10, $1/$5 per MTok, 배치 50%)은 `worker/generate/gateway.py`. 출력 토큰을 설계서 추정(1,200)에 맞추려고 thinking은 끈다(`generate.thinking`). JSON 강제(`structured_output`)는 설정으로 켤 수 있다.
- **정정 글**은 LLM이 아니라 창업자가 관리 화면에서 쓴다(`model='human'`). 원래 글의 출처를 그대로 잇는다.
- **교양 글**은 언론 보도를 입력으로 쓰지 않으므로 V2·V3·V5·V7·V9를 건너뛴다(검증 기록에 사유가 남는다). V7은 원문 기사를 입력으로 쓰는 글(사실·쟁점)에만 적용한다.
- **베타 검토 창구**: 낮에 만들어진 초안도 다음 날 06:20 자동 게시 또는 승인 때까지 drafts에 머문다. 아침 조간에는 모두 실린다.
- **쟁점 정리**는 04:30에 직전 24시간의 `disputed` 묶음 중 중요도 최고 하나를 골라 즉시 생성한다(06:00 검토에 들어가도록).
- **1면**은 선정 시각 기준으로 중요도를 다시 계산한다(시간 감쇠 반영). 정정이 붙은 글은 후보에서 뺀다. 06:25 이전 조립 요청이 오면 그 자리에서 한 번 계산해 저장하고 모두가 같이 쓴다.
- **읽기 커서**: 웹에서 연 조간과 이메일로 받은 조간을 모두 ‘읽은 것’으로 본다. 같은 날 설정을 바꿔 재조립하면 오늘 지면이 기준으로 삼았던 이전 조간까지만 읽은 것으로 본다.
- **매체 목록**: `rules/outlets.yaml`의 피드 중 2026-10-03에 실제로 항목을 돌려준 16곳만 켰다. 나머지는 `active: false`로 두고 주소 확인을 남겼다(스프린트 1 과제).
- **이미지 승인**: 자동으로 찾은 사진은 베타에서 모두 관리 화면 승인 뒤에 실린다. 출시 모드는 바로 싣되(`images.auto_approve`), Claude가 사진과 기사 대상을 한 번 대조하고(`images.vision_check`) 인물 사진은 여전히 승인 대기로 둔다. 자체 그래픽과 직접 등록한 이미지는 바로 실린다.
- **이미지 원본 유지**: 표시용 파일은 가로 1600px 이하로 비율을 유지해 줄이기만 한다. 화면에서 3:2로 맞춰 자르는 것은 변경 허용 라이선스(CC0·CC BY·공공누리 0·1유형·PD·스톡)일 때 1면 머리기사와 글 머리에서만이고, CC BY-SA와 보도용 이미지는 자르지 않는다.
- **이미지 자리**: 사진은 1면 머리기사와 글 머리에만 싣는다. 크레딧을 이미지 바로 아래에 둘 수 없는 작은 썸네일은 쓰지 않는다.
- **권리자 요청**: 웹이 접수와 동시에 이미지를 내린다(`/img/[id]`가 바로 404, 캐시 10분). 워커가 접수 회신·창업자 알림·대체 후보(승인 대기) 찾기를 하고, 관리 화면에서 복원·교체·내린 채로 중 하나를 고르고 회신을 쓴다.
- **보도용 제공 이미지**는 자동 검색하지 않는다. 뉴스룸·프레스킷의 약관을 사람이 읽고 다루는 소식(slug)과 함께 등록하면, 그 slug의 글에만 붙는다.
- **용어 규칙**은 이견이 없는 항목 하나만 넣었다. 어떤 표기가 중립인지는 편집 판단이므로 창업자가 근거와 함께 커밋한다.

## 아직 바깥에서 해야 하는 일

코드로 끝나지 않는 것들이다.

- Anthropic API 키, Amazon SES 도메인 인증·SMTP 자격 증명·SNS 구독(`/api/ses`), 카카오·구글 OAuth 앱 등록(리디렉션 `…/auth/{kakao,google}/callback`), 토스페이먼츠 계약, 공공데이터포털 서비스 키, Cloudflare R2 버킷, 텔레그램 봇
- 실제 API로 한 번 돌려 보기: 이 저장소의 생성·검증 흐름은 가짜 LLM으로만 끝에서 끝까지 확인했다. bge-m3 실제 임베딩에서 묶기 임계값(0.82/0.70)과 V10(0.75)을 첫 주 표본으로 다시 맞춰야 한다
- 비활성 매체 11곳의 RSS 주소 확인, 인터넷뉴스서비스사업 등록, 개인정보 처리방침 법무 검토, 편집 원칙의 책임자 이름·연락처(`FOUNDER_NAME`, `FOUNDER_EMAIL`)
- 구글 서치콘솔·네이버 서치어드바이저 등록 (`/sitemap.xml`, `/robots.txt`는 준비됨)
- 이미지: Unsplash·Pexels·Pixabay API 키 발급, Wikimedia Commons API 접근 확인(이 개발 환경에서는 403), 공공누리·기업 뉴스룸에서 자주 쓸 기관의 보도용 이미지 등록
