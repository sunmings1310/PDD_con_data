#!/usr/bin/env bash
set -euo pipefail
BASE_COMMIT="959f32d8f088e599382be8315fef59f6818db6c9"
SOURCE_PATH="docs/tasks/WEB-RESULT-VISIBILITY-001.md"
EXPECTED_SHA256="ee5c0f751d4db9e090659a1b25f69616a9faa42aacaaf0edb02d4d97c9628e36"
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