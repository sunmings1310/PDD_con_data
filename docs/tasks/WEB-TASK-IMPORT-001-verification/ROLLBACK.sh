#!/usr/bin/env bash
set -euo pipefail
TARGET="$1"
if [[ -z "$TARGET" ]]; then echo "usage: ROLLBACK.sh <target-copy>" >&2; exit 2; fi
ROOT="$(git rev-parse --show-toplevel)"
case "$TARGET" in
  "$ROOT"/*) ;;
  *) echo "ROLLBACK_REFUSED: target must stay under $ROOT" >&2; exit 2 ;;
esac
git show 2200ef021ed69f29fd3796b2c7a50252fa60575b:docs/backlog.md > "$TARGET"
echo "ROLLBACK_RESULT=restored_pre_task_start_backlog"
EXPECTED_SHA256="320d5209fd6423f969c3c941d7703901311339f9d84d69bfbc18abbc78c75d00"
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