#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:?usage: ROLLBACK.sh <probe-root>}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
base64 -d "$SCRIPT_DIR/ORIGINAL_BACKLOG.b64" > "$ROOT/docs/backlog.md"
rm -f "$ROOT/docs/tasks/SKU-PANEL-EVIDENCE-001.md"
BACKLOG_SHA=$(sha256sum "$ROOT/docs/backlog.md" | awk '{print $1}')
EXPECTED_SHA=$(base64 -d "$SCRIPT_DIR/ORIGINAL_BACKLOG.b64" | sha256sum | awk '{print $1}')
TASK_PRESENT=no
if [ -e "$ROOT/docs/tasks/SKU-PANEL-EVIDENCE-001.md" ]; then TASK_PRESENT=yes; fi
MATCH=no
if [ "$BACKLOG_SHA" = "$EXPECTED_SHA" ] && [ "$TASK_PRESENT" = no ]; then MATCH=yes; fi
printf 'RESTORED_SHA256=%s\nEXPECTED_SHA256=%s\nTASK_PRESENT=%s\nROLLBACK_MATCH=%s\n' "$BACKLOG_SHA" "$EXPECTED_SHA" "$TASK_PRESENT" "$MATCH"
[ "$MATCH" = yes ]