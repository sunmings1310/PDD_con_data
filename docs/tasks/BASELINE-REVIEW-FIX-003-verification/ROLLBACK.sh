#!/usr/bin/env bash
set -euo pipefail

BASE_COMMIT="c02bcd545fc9e1241fa7c09540f5fe783da6106f"
SOURCE_PATH="server/job_reconciliation.py"
EXPECTED_SHA256="31afdfdc0c688a6ab204245b1dfd7b820ebe6c9b4f5ee2d1bbdf0cd658b900f9"
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
