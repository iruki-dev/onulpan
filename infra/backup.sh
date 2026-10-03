#!/usr/bin/env bash
# 매일 03:10 pg_dump → Cloudflare R2 (S3 호환). 실패하면 즉시 알림. 30일 지난 덤프는 지운다.
set -uo pipefail
APP=/opt/onulpan
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
FILE=/tmp/onulpan-$STAMP.dump
ENDPOINT="https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
AWS="$APP/.venv/bin/aws --endpoint-url $ENDPOINT"

fail() {
  "$APP/.venv/bin/python" -m worker.jobs.cli alert backup_failed "DB 백업 실패: $1"
  rm -f "$FILE"
  exit 1
}

cd "$APP"
pg_dump --format=custom --no-owner "$DATABASE_URL" -f "$FILE" || fail "pg_dump"
$AWS s3 cp "$FILE" "s3://$R2_BUCKET/daily/onulpan-$STAMP.dump" --only-show-errors || fail "R2 업로드"
rm -f "$FILE"
CUTOFF=$(date -u -d '30 days ago' +%Y%m%d)
$AWS s3 ls "s3://$R2_BUCKET/daily/" | awk '{print $4}' | while read -r key; do
  d=$(echo "$key" | sed -E 's/onulpan-([0-9]{8}).*/\1/')
  [[ "$d" =~ ^[0-9]{8}$ && "$d" < "$CUTOFF" ]] && $AWS s3 rm "s3://$R2_BUCKET/daily/$key" --only-show-errors
done
echo "backup ok: onulpan-$STAMP.dump"
