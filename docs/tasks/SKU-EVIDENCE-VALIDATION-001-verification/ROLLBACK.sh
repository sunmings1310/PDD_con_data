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
 "docs/tasks/SKU-EVIDENCE-VALIDATION-001.md"
 "docs/tasks/SKU-EVIDENCE-VALIDATION-001-offline-matrix.md"
 "docs/tasks/SKU-EVIDENCE-VALIDATION-001-real-device-precheck.md"
 "docs/tasks/SKU-EVIDENCE-VALIDATION-001-fixture.json"
 "docs/tasks/SKU-EVIDENCE-VALIDATION-001-evidence-manifest.json"
)
EXPECTED=(
 "b5c18f32ff92b570b23801ed5b7954c131008db289c38a0a70aeba140140cb6f"
 "79b08d98bbe56acaf5da0279dcca0c603e39c0470e01e35c7630333fc00a8305"
 "9991a65365b448ee1e3df7cd59c760c5d786f52c349c73fe112b97c97159a9db"
 "46cf15032f3eee46f1ca92b6aa75445f5c02ea7bf81d0bc5020605e08d7b2c66"
 "296f19baef98c706ab4723f28f16aaf1e7c72b353c1e6b069290d7d35ddcdb0a"
 "91f4f0a7f9feebb557f060b2889f296ea5ccb179e04eafe69b051f7ec06de88f"
 "7302011cf79b38efc6be28b07b23780f5c3240a5898d91613e5b1e314e6a4c0c"
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
for file in "${FILES[@]:2}"; do rm -f "$TARGET_ROOT/$file"; echo "REMOVED_NEW_FILE=$file"; done
if ! git -C "$TARGET_ROOT" diff --quiet "$BASE" -- docs/CURRENT_STATE.md docs/backlog.md; then echo "ROLLBACK_MATCH=no"; exit 1; fi
for file in docs/CURRENT_STATE.md docs/backlog.md; do echo "RESTORED_SHA256[$file]=$(sha256sum "$TARGET_ROOT/$file" | awk '{print $1}')"; done
echo "ROLLBACK_MATCH=yes"
echo "ROLLBACK_RESULT=restored_sku_evidence_validation_baseline"
