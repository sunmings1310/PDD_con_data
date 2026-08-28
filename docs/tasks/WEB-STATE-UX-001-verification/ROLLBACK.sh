#!/usr/bin/env bash
set -euo pipefail
TARGET_ROOT="${1:?usage: ROLLBACK.sh <target-copy-root>}"
ROOT="$(cygpath -u "$(git rev-parse --show-toplevel)")"
case "$TARGET_ROOT" in "$ROOT"/*) ;; *) echo "ROLLBACK_REFUSED: target must stay under $ROOT" >&2; exit 2;; esac
BASE="807cfb4eff9c3830f9a7f3ad4f62f1f07d183b41"
for REL in docs/CURRENT_STATE.md docs/backlog.md docs/roadmap.md; do
  mkdir -p "$TARGET_ROOT/$(dirname "$REL")"
  git show "$BASE:$REL" > "$TARGET_ROOT/$REL"
  EXPECTED="$(git show "$BASE:$REL" | sha256sum | awk '{print $1}')"
  ACTUAL="$(sha256sum "$TARGET_ROOT/$REL" | awk '{print $1}')"
  echo "RESTORED_FILE=$REL"
  echo "RESTORED_SHA256=$ACTUAL"
  [[ "$EXPECTED" == "$ACTUAL" ]] || { echo "ROLLBACK_EXIT=1"; exit 1; }
done
rm -f "$TARGET_ROOT/docs/tasks/WEB-STATE-UX-001.md"
echo "REMOVED_NEW_FILE=docs/tasks/WEB-STATE-UX-001.md"
echo "ROLLBACK_RESULT=restored_task_setup_baseline"
echo "ROLLBACK_EXIT=0"
echo "ROLLBACK_MATCH=yes"
