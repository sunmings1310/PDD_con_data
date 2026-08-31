#!/usr/bin/env bash
set -euo pipefail
root="${1:-.}"
base="137a6f2a6fcb0978b8bcf9b0521cda1b4632f261"
cd "$root"
git checkout "$base" -- docs/backlog.md
git rm -f --ignore-unmatch \
  docs/tasks/PDD-MANUAL-REGRESSION-001.md \
  docs/tasks/PDD-MANUAL-REGRESSION-001-verification/DIFF_FILE.patch \
  docs/tasks/PDD-MANUAL-REGRESSION-001-verification/MODIFIED_FILE \
  docs/tasks/PDD-MANUAL-REGRESSION-001-verification/VERIFICATION.txt \
  docs/tasks/PDD-MANUAL-REGRESSION-001-verification/ROLLBACK.sh
printf 'ROLLBACK_RESULT=PASS\n'
