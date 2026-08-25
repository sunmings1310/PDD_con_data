#!/usr/bin/env bash
set -euo pipefail
TARGET="${1:?usage: ROLLBACK.sh <target-copy>}"
ROOT="$(git rev-parse --show-toplevel)"
case "$TARGET" in
  "$ROOT"/*) ;;
  *) echo "ROLLBACK_REFUSED: target must stay under $ROOT" >&2; exit 2 ;;
esac
git show 713cd714902c728cc0e7b796bdde4972c78042c9:docs/CURRENT_STATE.md > "$TARGET"
echo "ROLLBACK_RESULT=restored_pre_status_update_current_state"
