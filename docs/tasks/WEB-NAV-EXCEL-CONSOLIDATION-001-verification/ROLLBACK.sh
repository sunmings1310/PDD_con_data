#!/usr/bin/env bash
set -euo pipefail
BASE="f7d037cd612df09059dcea83189e63f99097042d"
TARGET_ROOT="${1:-}"
if [[ -z "$TARGET_ROOT" || ! -d "$TARGET_ROOT" ]] || ! git -C "$TARGET_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "BLOCKED: target_missing_or_not_worktree"
  exit 2
fi
TARGET_ROOT="$(cd "$TARGET_ROOT" && pwd -P)"
FILES=(
  "docs/CURRENT_STATE.md"
  "docs/backlog.md"
  "docs/tasks/WEB-NAV-EXCEL-CONSOLIDATION-001.md"
)
EXPECTED=(
  "75e7525401081ded541dcab5dc1d11c580b9653eb5cf2f3b642b5df70fcf504e"
  "681afb0d9eee3f324e13b4b4d0d5207a5781c760906f077a8d0341bc646df405"
  "e502f0398326ed2de73dde2925c8cadff2253350ba9498fb5fe3c9de22e21aae"
)
for i in "${!FILES[@]}"; do
  file="${FILES[$i]}"
  if [[ ! -f "$TARGET_ROOT/$file" ]]; then echo "BLOCKED: modified_file_missing:$file"; exit 2; fi
  before="$(sha256sum "$TARGET_ROOT/$file" | awk '{print $1}')"
  echo "BEFORE_SHA256[$file]=$before"
  echo "EXPECTED_MODIFIED_SHA256[$file]=${EXPECTED[$i]}"
  if [[ "$before" != "${EXPECTED[$i]}" ]]; then echo "BLOCKED: modified_hash_mismatch:$file"; exit 2; fi
done
git -C "$TARGET_ROOT" checkout "$BASE" -- docs/CURRENT_STATE.md docs/backlog.md
rm -f "$TARGET_ROOT/docs/tasks/WEB-NAV-EXCEL-CONSOLIDATION-001.md"
if ! git -C "$TARGET_ROOT" diff --quiet "$BASE" -- docs/CURRENT_STATE.md docs/backlog.md; then echo "ROLLBACK_MATCH=no"; exit 1; fi
echo "NEW_FILE_REMAINS=$([[ -e "$TARGET_ROOT/docs/tasks/WEB-NAV-EXCEL-CONSOLIDATION-001.md" ]] && echo 1 || echo 0)"
echo "ROLLBACK_MATCH=yes"
echo "ROLLBACK_RESULT=restored_web_nav_excel_consolidation_setup_baseline"
