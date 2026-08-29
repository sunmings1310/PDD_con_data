#!/usr/bin/env sh
set -eu
SOURCE_REPO="${1:?usage: ROLLBACK.sh SOURCE_REPO TARGET_ROOT}"
TARGET_ROOT="${2:?usage: ROLLBACK.sh SOURCE_REPO TARGET_ROOT}"
BASE="80b3435558e67850c9cba4215ca81456721ef0db"
git -C "$SOURCE_REPO" show "$BASE:docs/backlog.md" > "$TARGET_ROOT/docs/backlog.md"
rm -f "$TARGET_ROOT/docs/tasks/PDD-TARGET-MATCH-TERMINAL-001.md"
rm -rf "$TARGET_ROOT/docs/tasks/PDD-TARGET-MATCH-TERMINAL-001-verification"
EXPECTED=$(git -C "$SOURCE_REPO" show "$BASE:docs/backlog.md" | sha256sum | awk '{print $1}')
ACTUAL=$(sha256sum "$TARGET_ROOT/docs/backlog.md" | awk '{print $1}')
[ "$EXPECTED" = "$ACTUAL" ]
printf 'RESTORED_SHA256=%s\nROLLBACK_MATCH=yes\nTASK_PRESENT=no\nVERIFICATION_PRESENT=no\n' "$ACTUAL"
