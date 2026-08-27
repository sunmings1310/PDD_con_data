#!/usr/bin/env bash
set -euo pipefail

BASE_COMMIT="71c3e59f33e215953ee8af3800399999cd3a40b0"
SOURCE_PATH="server/management_queries.py"
EXPECTED_SHA256="952a18178fd1eb25692b6d43ca2ee9d42a98a09e9fcfe8bd375124bd2a821bde"
TARGET="${1:?usage: ROLLBACK.sh <rollback-copy-path>}"
ROOT="$(git rev-parse --show-toplevel)"

case "$TARGET" in
  /*) ;;
  *) TARGET="$ROOT/$TARGET" ;;
esac

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