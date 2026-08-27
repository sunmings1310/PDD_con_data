#!/usr/bin/env bash
set -u
TARGET="${1:-}"
if [[ -z "$TARGET" || ! -f "$TARGET" ]]; then
  echo "ROLLBACK_RESULT=BLOCKED: target copy is required"
  exit 2
fi
printf 'TASK_STATE=READY\n' > "$TARGET"
RESTORED_SHA256="$(sha256sum "$TARGET" | awk '{print $1}')"
EXPECTED_SHA256="$(printf 'TASK_STATE=READY\n' | sha256sum | awk '{print $1}')"
if [[ "$RESTORED_SHA256" == "$EXPECTED_SHA256" ]]; then
  echo "RESTORED_SHA256=$RESTORED_SHA256"
  echo "ROLLBACK_MATCH=true"
  echo "ROLLBACK_RESULT=READY restored"
  exit 0
fi
echo "RESTORED_SHA256=$RESTORED_SHA256"
echo "ROLLBACK_MATCH=false"
echo "ROLLBACK_RESULT=hash mismatch"
exit 1