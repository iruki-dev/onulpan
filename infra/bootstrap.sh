#!/usr/bin/env bash
# 새 서버(Ubuntu 24.04, x86_64 또는 ARM) 한 대에 오늘판 전체를 설치한다. 목표: 서버 이전 1시간 이내.
#   1) sudo infra/bootstrap.sh            2) /etc/onulpan.env 작성 (.env.example 참고, infra/check-env.sh로 검사)
#   3) sudo infra/restore.sh (R2의 최신 덤프) 또는 새로 시작이면 생략
#   4) sudo systemctl start onulpan.target   — 터널(onulpan-tunnel)이 같이 켜지며 바로 공개된다. DNS는 바꾸지 않는다
# 서버 이전 순서와 터널 처음 만들기는 README ‘운영’.
set -euo pipefail
APP=/opt/onulpan
SRC="$(cd "$(dirname "$0")/.." && pwd)"

apt-get update
apt-get install -y postgresql-16 postgresql-16-pgvector python3-venv python3-pip git curl ca-certificates \
  fonts-noto-cjk build-essential
# 공개 주소: Cloudflare Tunnel (cloudflared, Cloudflare 공식 apt 저장소)
if ! command -v cloudflared >/dev/null; then
  install -d -m 0755 /usr/share/keyrings
  curl -fsSL https://pkg.cloudflare.com/cloudflare-public-v2.gpg -o /usr/share/keyrings/cloudflare-public-v2.gpg
  echo "deb [signed-by=/usr/share/keyrings/cloudflare-public-v2.gpg] https://pkg.cloudflare.com/cloudflared any main" \
    > /etc/apt/sources.list.d/cloudflared.list
  apt-get update
  apt-get install -y cloudflared
fi
if ! command -v node >/dev/null || [[ "$(node -v)" != v22* ]]; then
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
  apt-get install -y nodejs
fi

id onulpan >/dev/null 2>&1 || useradd --system --home "$APP" --shell /usr/sbin/nologin onulpan
mkdir -p "$APP"
rsync -a --delete --exclude node_modules --exclude .next --exclude var "$SRC"/ "$APP"/
mkdir -p "$APP/var" "$APP/var/images" "$APP/reports"

# 파이썬 워커 (bge-m3 CPU 추론 포함)
python3 -m venv "$APP/.venv"
"$APP/.venv/bin/pip" install --upgrade pip
"$APP/.venv/bin/pip" install --extra-index-url https://download.pytorch.org/whl/cpu -e "$APP[embed]" awscli

# 웹
cd "$APP/web" && npm ci && NEXT_TELEMETRY_DISABLED=1 npm run build
cp -r "$APP/web/.next/static" "$APP/web/.next/standalone/.next/"
cp -r "$APP/web/public" "$APP/web/.next/standalone/" 2>/dev/null || true
chown -R onulpan:onulpan "$APP"

# 데이터베이스: 소유자(마이그레이션), 워커(app_writer), 웹(app_reader)
if [[ -f /etc/onulpan.env ]]; then
  "$SRC/infra/check-env.sh" /etc/onulpan.env      # 값 뒤 주석이 있으면 여기서 멈춘다
  set -a; . /etc/onulpan.env; set +a
fi
WORKER_PW="${WORKER_DB_PASSWORD:-$(openssl rand -hex 16)}"
WEB_PW="${WEB_DB_PASSWORD:-$(openssl rand -hex 16)}"
sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
SELECT 'CREATE DATABASE onulpan' WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'onulpan')\gexec
SQL
# 마이그레이션과 등록부 동기화는 postgres(peer 인증)로 돌린다. 역할(app_writer, app_reader)과 권한은 마이그레이션이 만든다.
# /etc/onulpan.env가 아직 없거나 워커 암호가 정해지기 전(첫 설치)에도 돌아가고, 실패하면 설치가 멈춘다.
admin_cli() {
  (cd "$APP" && sudo -u postgres env DATABASE_URL="postgresql:///onulpan?host=/var/run/postgresql" \
    "$APP/.venv/bin/python" -m worker.jobs.cli "$@")
}
admin_cli migrate               # 이미지 출처 등록부(rules/image_sources.yaml)도 함께 동기화한다
admin_cli sync-outlets          # 수집 대상 매체 (rules/outlets.yaml)
sudo -u postgres psql -v ON_ERROR_STOP=1 -d onulpan <<SQL
DO \$\$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'onulpan_worker') THEN
    CREATE ROLE onulpan_worker LOGIN PASSWORD '$WORKER_PW' IN ROLE app_writer; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'onulpan_web') THEN
    CREATE ROLE onulpan_web LOGIN PASSWORD '$WEB_PW' IN ROLE app_reader; END IF;
END \$\$;
SQL
echo "DB 암호(처음 설치일 때만 새로 만듦) — /etc/onulpan.env의 DATABASE_URL, DATABASE_URL_WEB에 넣는다:"
echo "  onulpan_worker: $WORKER_PW"
echo "  onulpan_web:    $WEB_PW"

# systemd
cp "$APP"/infra/systemd/*.service "$APP"/infra/systemd/*.timer "$APP"/infra/systemd/*.target /etc/systemd/system/
systemctl daemon-reload
systemctl enable onulpan.target onulpan-web.service onulpan-jobs.service onulpan-tunnel.service
for t in "$APP"/infra/systemd/*.timer; do systemctl enable "$(basename "$t")"; done
echo "설치 완료. /etc/onulpan.env를 채운 뒤: systemctl start onulpan.target"
