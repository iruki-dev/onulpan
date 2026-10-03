#!/usr/bin/env bash
# 서버 이전: R2의 최신 덤프를 받아 복원한다. bootstrap.sh 다음에 실행.
set -euo pipefail
set -a; . /etc/onulpan.env; set +a
APP=/opt/onulpan
AWS="$APP/.venv/bin/aws --endpoint-url https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
LATEST=$($AWS s3 ls "s3://$R2_BUCKET/daily/" | awk '{print $4}' | sort | tail -1)
[[ -n "$LATEST" ]] || { echo "덤프가 없습니다"; exit 1; }
$AWS s3 cp "s3://$R2_BUCKET/daily/$LATEST" /tmp/restore.dump
systemctl stop onulpan.target || true
sudo -u postgres pg_restore --clean --if-exists --no-owner --role=onulpan -d onulpan /tmp/restore.dump
sudo -u postgres psql -d onulpan -c "REASSIGN OWNED BY postgres TO onulpan" >/dev/null || true
rm -f /tmp/restore.dump
# 이미지 파일
if [[ -n "${IMAGE_DIR:-}" ]]; then
  mkdir -p "$IMAGE_DIR" && $AWS s3 sync "s3://$R2_BUCKET/images/" "$IMAGE_DIR" --only-show-errors && chown -R onulpan:onulpan "$IMAGE_DIR"
fi
echo "복원 완료: $LATEST — systemctl start onulpan.target 후 Cloudflare DNS 전환"
