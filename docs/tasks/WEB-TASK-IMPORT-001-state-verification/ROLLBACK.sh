#!/usr/bin/env bash
set -euo pipefail
TARGET_ROOT="${1:?usage: ROLLBACK.sh <target-copy-root>}"
ROOT="$(git rev-parse --show-toplevel)"
case "$TARGET_ROOT" in
  "$ROOT"/*) ;;
  *) echo "ROLLBACK_REFUSED: target must stay under $ROOT" >&2; exit 2 ;;
esac
BASE="40e3e958aa27b37cd0dcbf06150317789898895f"
FILES=("docs/CURRENT_STATE.md" "docs/backlog.md" "docs/roadmap.md")
for REL in "${FILES[@]}"; do
  mkdir -p "$TARGET_ROOT/$(dirname "$REL")"
  git show "$BASE:$REL" > "$TARGET_ROOT/$REL"
  EXPECTED="$(git show "$BASE:$REL" | sha256sum | awk '{print $1}')"
  RESTORED="$(sha256sum "$TARGET_ROOT/$REL" | awk '{print $1}')"
  echo "RESTORED_FILE=$REL"
  echo "RESTORED_SHA256=$RESTORED"
  echo "EXPECTED_SHA256=$EXPECTED"
  if [[ "$RESTORED" != "$EXPECTED" ]]; then
    echo "ROLLBACK_EXIT=1"
    echo "ROLLBACK_MATCH=no"
    exit 1
  fi
done
echo "ROLLBACK_RESULT=restored_pre_state_sync_documents"
echo "ROLLBACK_EXIT=0"
echo "ROLLBACK_MATCH=yes"
