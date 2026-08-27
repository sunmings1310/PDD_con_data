#!/usr/bin/env bash
set -euo pipefail
BASE_COMMIT="73c9e86c9ff2e7504be6d67bf504e7d5240f8c70"
SOURCE_PATH="web/src/utils/requestGeneration.js"
EXPECTED_SHA256="efc9ed1197e3e2e8e212842b71b643de4b321a8d5421b88f87062598110ec6b0"
TARGET="${1:?usage: ROLLBACK.sh <rollback-copy-path>}"
ROOT="$(git rev-parse --show-toplevel)"
case "$TARGET" in /*) ;; *) TARGET="$ROOT/$TARGET" ;; esac
test -f "$TARGET"
BEFORE_SHA256="$(sha256sum "$TARGET" | awk '{print $1}')"
git show "$BASE_COMMIT:$SOURCE_PATH" > "$TARGET"
AFTER_SHA256="$(sha256sum "$TARGET" | awk '{print $1}')"
test "$AFTER_SHA256" = "$EXPECTED_SHA256"
printf 'target=%s\n' "${TARGET#"$ROOT/"}"
printf 'before_sha256=%s\n' "$BEFORE_SHA256"
printf 'after_sha256=%s\n' "$AFTER_SHA256"
printf 'expected_sha256=%s\n' "$EXPECTED_SHA256"
printf 'result=RESTORED\n'
printf 'exit_status=0\n'