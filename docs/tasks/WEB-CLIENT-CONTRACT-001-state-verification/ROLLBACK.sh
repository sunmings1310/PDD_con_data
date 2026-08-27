#!/usr/bin/env bash
set -euo pipefail
TARGET="$1"
if [[ -z "$TARGET" ]]; then echo "usage: ROLLBACK.sh <target-copy>" >&2; exit 2; fi
ROOT="$(git rev-parse --show-toplevel)"
case "$TARGET" in
  "$ROOT"/*) ;;
  *) echo "ROLLBACK_REFUSED: target must stay under $ROOT" >&2; exit 2 ;;
esac
git show a02c8a84ade34a7e1c67ec57ad4040a84ffe5078:docs/CURRENT_STATE.md > "$TARGET"
echo "ROLLBACK_RESULT=restored_pre_status_update_current_state"
EXPECTED_SHA256="610dd9b545c0f36f647860f1f999efd3cc6e39cc394f0dc9b2f1a1c6ae1ee495"
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