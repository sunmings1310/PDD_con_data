#!/usr/bin/env bash
set -euo pipefail
TARGET="$1"
if [[ -z "$TARGET" ]]; then echo "usage: ROLLBACK.sh <target-copy>" >&2; exit 2; fi
ROOT="$(git rev-parse --show-toplevel)"
case "$TARGET" in "$ROOT"/*) ;; *) echo "ROLLBACK_REFUSED: target must stay under $ROOT" >&2; exit 2;; esac
git show d3eff55958c619463ffb28f498e72e32618792e1:docs/tasks/WEB-TASK-IMPORT-001.md > "$TARGET"
echo "ROLLBACK_RESULT=restored_setup_task"
EXPECTED_SHA256="6b335ee009447331ef48c5e814e283ca3ca99f347e00a887ac9f26af0291d2a4"
RESTORED_SHA256="$(sha256sum "$TARGET" | awk '{print $1}')"
echo "RESTORED_SHA256=$RESTORED_SHA256"
[[ "$RESTORED_SHA256" == "$EXPECTED_SHA256" ]] && echo "ROLLBACK_EXIT=0" && exit 0
echo "ROLLBACK_EXIT=1"; exit 1