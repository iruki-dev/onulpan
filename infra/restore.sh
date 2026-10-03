#!/usr/bin/env bash
# 서버 이전: R2의 최신 덤프와 이미지 파일을 받아 복원한다. bootstrap.sh 다음에 root로 실행.
#
# 소유 구조는 bootstrap과 같다: 객체는 postgres 소유(--no-owner, postgres로 실행)이고, 권한은 덤프에 담긴
# GRANT(app_writer·app_reader)로 되살아난다. 로그인 역할(onulpan_worker·onulpan_web)은 bootstrap이 이미 만들었다.
# 한 트랜잭션으로 복원하므로 실패하면 DB는 복원 전 그대로이고, 내렸던 서비스를 다시 올린다.
set -euo pipefail
APP=/opt/onulpan
"$APP/infra/check-env.sh" /etc/onulpan.env
set -a; . /etc/onulpan.env; set +a
AWS="$APP/.venv/bin/aws --endpoint-url https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
DB_ADMIN_URL="postgresql:///onulpan?host=/var/run/postgresql"

DUMP=$(mktemp /tmp/onulpan-restore.XXXXXX.dump)
trap 'rm -f "$DUMP"' EXIT

# 1. 받고 검사한다 (서비스를 내리기 전에)
LATEST=$($AWS s3 ls "s3://$R2_BUCKET/daily/" | awk '{print $4}' | sort | tail -1)
[[ -n "$LATEST" ]] || { echo "덤프가 없습니다"; exit 1; }
$AWS s3 cp "s3://$R2_BUCKET/daily/$LATEST" "$DUMP" --only-show-errors
chmod 644 "$DUMP"
sudo -u postgres pg_restore --list "$DUMP" >/dev/null || { echo "덤프를 읽지 못했습니다: $LATEST"; exit 1; }
if [[ -n "${IMAGE_DIR:-}" ]]; then
  mkdir -p "$IMAGE_DIR"
  $AWS s3 sync "s3://$R2_BUCKET/images/" "$IMAGE_DIR" --only-show-errors
  chown -R onulpan:onulpan "$IMAGE_DIR"
fi

# 2. 복원하는 동안 쓰는 쪽(웹·작업 큐·타이머·터널)을 내린다
TIMERS=$(systemctl list-unit-files 'onulpan-*.timer' --no-legend 2>/dev/null | awk '{print $1}' | xargs)
restart_services() {
  systemctl start onulpan.target
  [[ -n "$TIMERS" ]] && systemctl start $TIMERS
}
systemctl stop onulpan.target $TIMERS || true

# 3. 한 트랜잭션으로 복원. 실패하면 이전 상태 그대로 다시 올린다
if ! sudo -u postgres pg_restore --clean --if-exists --no-owner --single-transaction --exit-on-error \
    -d onulpan "$DUMP"; then
  echo "복원 실패: DB는 복원 전 상태 그대로입니다. 서비스를 다시 올립니다."
  restart_services
  exit 1
fi

# 4. 덤프 이후에 추가된 마이그레이션(새 코드)이 있으면 적용한다 (이미지 출처 등록부도 맞춘다)
(cd "$APP" && sudo -u postgres env DATABASE_URL="$DB_ADMIN_URL" "$APP/.venv/bin/python" -m worker.jobs.cli migrate)

echo "복원 완료: $LATEST"
echo "옛 서버의 onulpan.target(터널 포함)이 꺼져 있는지 확인한 뒤: systemctl start onulpan.target $TIMERS"
