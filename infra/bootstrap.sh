#!/usr/bin/env bash
# 새 서버(Ubuntu 24.04, x86_64 또는 ARM) 한 대에 오늘판 전체를 설치한다. 목표: 서버 이전 1시간 이내.
#   1) sudo infra/bootstrap.sh            2) /etc/onulpan.env 작성 (.env.example 참고)
#   3) sudo infra/restore.sh (R2의 최신 덤프) 또는 새로 시작이면 생략
#   4) sudo systemctl start onulpan.target   5) Cloudflare DNS를 새 서버로
set -euo pipefail
APP=/opt/onulpan
SRC="$(cd "$(dirname "$0")/.." && pwd)"

apt-get update
apt-get install -y postgresql-16 postgresql-16-pgvector python3-venv python3-pip git curl ca-certificates \
  fonts-noto-cjk build-essential
if ! command -v node >/dev/null || [[ "$(node -v)" != v22* ]]; then
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
  apt-get install -y nodejs
fi

id onulpan >/dev/null 2>&1 || useradd --system --home "$APP" --shell /usr/sbin/nologin onulpan
mkdir -p "$APP"
rsync -a --delete --exclude node_modules --exclude .next --exclude var "$SRC"/ "$APP"/
mkdir -p "$APP/var" "$APP/reports"

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
if [[ -f /etc/onulpan.env ]]; then set -a; . /etc/onulpan.env; set +a; fi
WORKER_PW="${WORKER_DB_PASSWORD:-$(openssl rand -hex 16)}"
WEB_PW="${WEB_DB_PASSWORD:-$(openssl rand -hex 16)}"
sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
SELECT 'CREATE DATABASE onulpan' WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'onulpan')\gexec
SQL
# 마이그레이션은 postgres(peer 인증)로 돌린다. 역할(app_writer, app_reader)과 권한은 마이그레이션이 만든다.
(cd "$APP" && sudo -u postgres env DATABASE_URL="postgresql:///onulpan?host=/var/run/postgresql" \
  "$APP/.venv/bin/python" -m worker.jobs.cli migrate)
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

# 수집 대상 매체
sudo -u onulpan env $(grep -v '^#' /etc/onulpan.env 2>/dev/null | xargs) "$APP/.venv/bin/python" -m worker.jobs.cli sync-outlets || true

# systemd
cp "$APP"/infra/systemd/*.service "$APP"/infra/systemd/*.timer "$APP"/infra/systemd/*.target /etc/systemd/system/
systemctl daemon-reload
systemctl enable onulpan.target onulpan-web.service onulpan-jobs.service
for t in "$APP"/infra/systemd/*.timer; do systemctl enable "$(basename "$t")"; done
echo "설치 완료. /etc/onulpan.env를 채운 뒤: systemctl start onulpan.target"
