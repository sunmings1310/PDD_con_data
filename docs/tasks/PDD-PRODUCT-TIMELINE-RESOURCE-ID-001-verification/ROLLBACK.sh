#!/usr/bin/env bash
set -euo pipefail
root="${1:-.}"
base="80b3435558e67850c9cba4215ca81456721ef0db"
cd "$root"
git checkout "$base" -- docs/backlog.md
git rm -f --ignore-unmatch \
  docs/tasks/PDD-PRODUCT-TIMELINE-RESOURCE-ID-001.md \
  docs/tasks/PDD-PRODUCT-TIMELINE-RESOURCE-ID-001-verification/DIFF_FILE.patch \
  docs/tasks/PDD-PRODUCT-TIMELINE-RESOURCE-ID-001-verification/MODIFIED_FILE \
  docs/tasks/PDD-PRODUCT-TIMELINE-RESOURCE-ID-001-verification/VERIFICATION.txt \
  docs/tasks/PDD-PRODUCT-TIMELINE-RESOURCE-ID-001-verification/ROLLBACK.sh
printf 'ROLLBACK_RESULT=PASS\n'
