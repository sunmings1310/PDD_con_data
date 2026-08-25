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
EXPECTED_SHA256="8ffccc145ef323314543231148aed8d09cbfca3bad2856edbfd6c412873754ae"
RESTORED_SHA256="$(sha256sum "$TARGET" | awk '{print $1}')"
echo "RESTORED_SHA256=$RESTORED_SHA256"
if [[ "$RESTORED_SHA256" == "$EXPECTED_SHA256" ]]; then
  echo "ROLLBACK_EXIT=0"
  echo "ROLLBACK_MATCH=yes"
  exit 0
fi
echo "ROLLBACK_EXIT=1"
echo "ROLLBACK_MATCH=no"
exit 1
