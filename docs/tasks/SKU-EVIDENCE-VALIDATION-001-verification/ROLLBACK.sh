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
 "d8356d4f02dd3417d78e99f5f8f97708ee64979624895cd29696f4e1a9085376"
 "974bb69634ab241c1ddc90dc910241c9f7cd50441a277221032fa82900750822"
 "8b1f98ad373c821c8253e2ca80f79ffdb845a2390d11320ef830d18a3125591e"
 "46cf15032f3eee46f1ca92b6aa75445f5c02ea7bf81d0bc5020605e08d7b2c66"
 "78de87e8d97801519a06b3599c975732ad96e7b6176bed65fb57cb57f42c8b56"
 "91f4f0a7f9feebb557f060b2889f296ea5ccb179e04eafe69b051f7ec06de88f"
 "6760cc444a15ce042ee512297a7fbebefb6f9e251c4a639b6aaf9e66f545fd20"
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