#!/usr/bin/env bash
set -euo pipefail
# Restore only an explicitly supplied Review Fix probe copy; the repository
# MODIFIED_FILE remains the changed REREVIEW artifact.
TARGET="${1:?usage: ROLLBACK.sh <rollback-copy-path>}"
EXPECTED_SHA256="436d54e45c32f384c50533952c73647b8fe35b144a8be7d93fe3c3e45c18185d"
ROOT="$(git rev-parse --show-toplevel)"
case "$TARGET" in /*) ;; *) TARGET="$ROOT/$TARGET" ;; esac
test -f "$TARGET"
BEFORE_SHA256="$(sha256sum "$TARGET" | awk '{print $1}')"
printf 'TASK_STATE=READY\nCONTRACT_STATUS=UNFROZEN\n' > "$TARGET"
AFTER_SHA256="$(sha256sum "$TARGET" | awk '{print $1}')"
test "$AFTER_SHA256" = "$EXPECTED_SHA256"
printf 'target=%s\n' "${TARGET#"$ROOT/"}"
printf 'before_sha256=%s\n' "$BEFORE_SHA256"
printf 'after_sha256=%s\n' "$AFTER_SHA256"
printf 'expected_sha256=%s\n' "$EXPECTED_SHA256"
printf 'result=RESTORED\n'
printf 'exit_status=0\n'
