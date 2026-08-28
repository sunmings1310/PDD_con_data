#!/usr/bin/env bash
set -euo pipefail
BASE="d56787a614aba8559934a085a66e12bd20c12832"
TARGET_ROOT="${1:-}"
if [[ -z "$TARGET_ROOT" || ! -d "$TARGET_ROOT" ]] || ! git -C "$TARGET_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "BLOCKED: target_missing_or_not_worktree"
  exit 2
fi
TARGET_ROOT="$(cd "$TARGET_ROOT" && pwd -P)"
FILES=("docs/CURRENT_STATE.md" "docs/backlog.md" "docs/roadmap.md")
EXPECTED_MODIFIED=(
  "892d33bbce7b460a9c74b36c43004ad17d61910dd44492aa0234534652507909"
  "6c71464d4cefea811497abe12cb0b9ac8ce04b005833ed0cbab5d4689e97630e"
  "bc81af6af43fba89a568ee07edcc034208c6455dd23d9d6477cfda2d4649b48f"
)
for i in "${!FILES[@]}"; do
  file="${FILES[$i]}"
  before="$(sha256sum "$TARGET_ROOT/$file" | awk '{print $1}')"
  echo "BEFORE_SHA256[$file]=$before"
  echo "EXPECTED_MODIFIED_SHA256[$file]=${EXPECTED_MODIFIED[$i]}"
  if [[ "$before" != "${EXPECTED_MODIFIED[$i]}" ]]; then
    echo "BLOCKED: modified_hash_mismatch:$file"
    exit 2
  fi
done
git -C "$TARGET_ROOT" checkout "$BASE" -- "${FILES[@]}"
for file in "${FILES[@]}"; do
  restored="$(sha256sum "$TARGET_ROOT/$file" | awk '{print $1}')"
  echo "RESTORED_SHA256[$file]=$restored"
done
if ! git -C "$TARGET_ROOT" diff --quiet "$BASE" -- "${FILES[@]}"; then
  echo "ROLLBACK_MATCH=no"
  exit 1
fi
echo "ROLLBACK_MATCH=yes"
echo "ROLLBACK_RESULT=restored_docs_state_sync_baseline"
