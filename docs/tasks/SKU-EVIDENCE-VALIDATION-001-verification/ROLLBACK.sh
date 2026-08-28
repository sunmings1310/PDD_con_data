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
 "5b19234b05ff7b62da92335b3ee4bfbbddc9b781259dd484044ae10f2dea11ce"
 "ff9358cf25d5238f47af8e7e07aeb200ca78f0ee076935657bfeac69e7d1fb46"
 "58cbd89593f1266af58816426e2ee7480956ac7377232e1891cc35dfd0b119d4"
 "46cf15032f3eee46f1ca92b6aa75445f5c02ea7bf81d0bc5020605e08d7b2c66"
 "336bcd3b18aaac8218adfcb4dfafd9543e6afe6f11b41443402b8d05baa673c2"
 "91f4f0a7f9feebb557f060b2889f296ea5ccb179e04eafe69b051f7ec06de88f"
 "5a72cbe5484bccc7a2aa4579b2dadd70c0736de347a5f46524c7398e937c6a4e"
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
