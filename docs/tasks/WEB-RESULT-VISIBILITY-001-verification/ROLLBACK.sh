#!/usr/bin/env bash
set -euo pipefail

BASE_COMMIT="6f5ae0138eb14a178918b648745e4e5c1a502e73"
SOURCE_PATH="server/management_queries.py"
EXPECTED_SHA256="eee661981c6b0e093cf921cdd0e02e1ded01f4b0811efbb47ed9521a3a7f76ce"
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