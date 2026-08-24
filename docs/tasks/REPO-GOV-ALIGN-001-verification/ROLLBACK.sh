#!/usr/bin/env bash
# REPO-GOV-ALIGN-001 review-fix verification: 2026-08-25
set -euo pipefail
TARGET="${1:?usage: ROLLBACK.sh <target-copy>}"
ROOT="$(git rev-parse --show-toplevel)"
case "$TARGET" in
  "$ROOT"/*) ;;
  *) echo "ROLLBACK_REFUSED: target must stay under $ROOT" >&2; exit 2 ;;
esac
git show 28addc917706904bf84252cb1e1cbff01c75aa3d:WORKFLOW.md > "$TARGET"
echo "ROLLBACK_RESULT=restored_old_governance_workflow"
sha256sum "$TARGET" | awk '{print "RESTORED_SHA256=" $1}'