#!/usr/bin/env bash
# /etc/onulpan.env 형식 검사. systemd EnvironmentFile은 값 뒤의 ‘# 설명’을 값의 일부로 읽으므로 막는다.
#   infra/check-env.sh [파일]          문제 줄을 보여 주고 실패(1)
#   infra/check-env.sh --fix [파일]    값 뒤 주석을 값 위 줄로 옮긴다 (원본은 .bak로 남긴다)
set -euo pipefail
FIX=0
if [[ "${1:-}" == "--fix" ]]; then FIX=1; shift; fi
FILE="${1:-/etc/onulpan.env}"
[[ -f "$FILE" ]] || { echo "없음: $FILE"; exit 1; }

# 따옴표 없는 값 뒤에 공백 + # 이 오는 줄
BAD=$(grep -nE '^[A-Za-z_][A-Za-z0-9_]*=[^"'"'"']*[[:space:]]#' "$FILE" || true)
if [[ -z "$BAD" ]]; then
  echo "ok: $FILE"
  exit 0
fi
if [[ $FIX -eq 0 ]]; then
  echo "값 뒤에 주석이 붙은 줄이 있습니다 (systemd가 값으로 읽습니다):"
  echo "$BAD"
  echo "고치려면: sudo $0 --fix $FILE"
  exit 1
fi
cp -p "$FILE" "$FILE.bak"
awk '
  /^[A-Za-z_][A-Za-z0-9_]*=[^"'"'"']*[[:space:]]#/ {
    i = index($0, "#")
    val = substr($0, 1, i - 1); sub(/[[:space:]]+$/, "", val)
    print substr($0, i)
    print val
    next
  }
  { print }
' "$FILE.bak" > "$FILE"
echo "고쳤습니다: $FILE (원본: $FILE.bak)"
