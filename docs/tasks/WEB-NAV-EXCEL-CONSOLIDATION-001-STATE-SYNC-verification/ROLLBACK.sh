#!/usr/bin/env bash
set -euo pipefail

BASE="d91b6389bae80067352b2bb4bc5848ca3132f37a"
TARGET_ROOT="${1:-}"

if [[ -z "$TARGET_ROOT" || ! -d "$TARGET_ROOT" ]] || ! git -C "$TARGET_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "BLOCKED: target_missing_or_not_worktree"
  exit 2
fi

TARGET_ROOT="$(cd "$TARGET_ROOT" && pwd -P)"
FILES=("docs/CURRENT_STATE.md" "docs/backlog.md" "docs/roadmap.md")
EXPECTED_MODIFIED=(
  "7f8e0b10096f93a2ea67e2880423a7b73d86bea6572006053272710f05ea8733"
  "603dc805f7fc8bd0833326cd8684b53ebd63159ce3852e95abf981e94edff8ef"
  "780ad43d3f49fcb06300a411a9fbf9f4e1b925707898ab7d477d27994ae881e0"
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
echo "ROLLBACK_RESULT=restored_web_nav_excel_state_sync_baseline"
