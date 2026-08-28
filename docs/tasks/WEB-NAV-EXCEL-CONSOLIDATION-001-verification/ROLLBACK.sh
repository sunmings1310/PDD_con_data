#!/usr/bin/env bash
set -euo pipefail
BASE="f7d037cd612df09059dcea83189e63f99097042d"
TARGET_ROOT="${1:-}"
if [[ -z "$TARGET_ROOT" || ! -d "$TARGET_ROOT" ]] || ! git -C "$TARGET_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "BLOCKED: target_missing_or_not_worktree"; exit 2
fi
TARGET_ROOT="$(cd "$TARGET_ROOT" && pwd -P)"
FILES=(
  "docs/CURRENT_STATE.md"
  "docs/backlog.md"
  "docs/tasks/WEB-NAV-EXCEL-CONSOLIDATION-001.md"
  "tests/test_task_import_contract.py"
  "web/scripts/test-task-import-components.mjs"
  "web/scripts/test-nav-excel-consolidation-components.mjs"
  "web/src/layout/AdminLayout.vue"
  "web/src/router/index.js"
  "web/src/views/data/ProductList.vue"
  "web/src/views/excel/ExcelMatch.vue"
  "web/src/views/tasks/TaskCreate.vue"
)
EXPECTED_MODIFIED=(
  "1856490d2761565c342c6852b63dd11c58f5d1124b4632c310528e90c7c773d1"
  "c8f00307abdf684f402401c06cbd07b274f292ef37eeb2aac04e7026b29ef7e4"
  "84f15503b84d1db0ce06bb5078aa7aeda52a4870e50d3f047ac83b78dc280589"
  "c00aac9dac4bba750fc9368a5c74db3dd95410720d4c09a125eca4b193f23d42"
  "c7908f934e3bd2805fc1b7dadc06c4856a1a5951d015adaf79ead7c7237a2fb8"
  "76ca732b5d72fb738d5342c84782344a58ab8985a2bedc18d59743b4aba0cde5"
  "2105734742d38ce9dfc2432d3cbacf4fbf727327226af0c4520cec41c6119527"
  "af394fee25d1d4f347665bfef4762a2c7e8b41c1b1a188166ff42541cfcf78a8"
  "96ce0c3aa37624990567c88f47d48ab8af1ebbe5e0f1f6b924395b40176cab46"
  "8f2476d55a0f30082d036335a6169e06b881b78398ced6b75b29d2438cde4ac2"
  "a3333cf247082de1d45753bb470f56bde3046279a505a0ac4ce1c44ac9e09182"
)
EXPECTED_BASE=(
  "9a137d7e96673888543efee9d0ab38d460ad119a3a001c48462e940fcc6c166b"
  "c0c1cc173a29ca9916301afda3dac0d8bc661a60351d0cb624495d13bebed21d"
  "ABSENT"
  "5a99ce706c899e346dc692590f798deda0ceadc81efaa31db67c6d9666484824"
  "327fde1cfc7c00ecef698a238c8394e1c21c49ab288791a6f0c760d61fa45c58"
  "ABSENT"
  "d5d6ff5ed0737ca94e0c98d1d65c3a720a008e7b5f8b310a34980d33f6989c33"
  "7aad6f3fa025b7327170ade5c18fc9a22704744bebfa11ceaa09e8a3abe4f434"
  "5457c5ebd59d18ae84456d8b01489cf8f9d5c27b0ba3881dd09778af75c4c99e"
  "ace957c8e512cf9aa437e487b0e555a2a271d02aa60847d6061057443b4041e8"
  "1567b236f2f9182f461828f27fba3c43677840cbe84a8b4f73fdda59dc0f1c28"
)
for i in "${!FILES[@]}"; do
  file="${FILES[$i]}"
  if [[ ! -f "$TARGET_ROOT/$file" ]]; then echo "BLOCKED: modified_file_missing:$file"; exit 2; fi
  before="$(sha256sum "$TARGET_ROOT/$file" | awk '{print $1}')"
  echo "BEFORE_SHA256[$file]=$before"
  echo "EXPECTED_MODIFIED_SHA256[$file]=${EXPECTED_MODIFIED[$i]}"
  if [[ "$before" != "${EXPECTED_MODIFIED[$i]}" ]]; then echo "BLOCKED: modified_hash_mismatch:$file"; exit 2; fi
done
git -C "$TARGET_ROOT" checkout "$BASE" -- "docs/CURRENT_STATE.md" "docs/backlog.md" "tests/test_task_import_contract.py" "web/scripts/test-task-import-components.mjs" "web/src/layout/AdminLayout.vue" "web/src/router/index.js" "web/src/views/data/ProductList.vue" "web/src/views/excel/ExcelMatch.vue" "web/src/views/tasks/TaskCreate.vue"
rm -f "$TARGET_ROOT/docs/tasks/WEB-NAV-EXCEL-CONSOLIDATION-001.md" "$TARGET_ROOT/web/scripts/test-nav-excel-consolidation-components.mjs"
match=yes
for i in "${!FILES[@]}"; do
  file="${FILES[$i]}"
  if [[ -e "$TARGET_ROOT/$file" ]]; then restored="$(sha256sum "$TARGET_ROOT/$file" | awk '{print $1}')"; else restored="ABSENT"; fi
  echo "RESTORED_SHA256[$file]=$restored"
  echo "EXPECTED_BASE_SHA256[$file]=${EXPECTED_BASE[$i]}"
  file_match=yes; [[ "$restored" == "${EXPECTED_BASE[$i]}" ]] || file_match=no
  echo "MATCH[$file]=$file_match"
  [[ "$file_match" == yes ]] || match=no
done
echo "ROLLBACK_MATCH=$match"
[[ "$match" == yes ]] || exit 1
echo "ROLLBACK_RESULT=restored_base_files_and_removed_new_files"
