#!/usr/bin/env bash
set -euo pipefail
root="${1:-.}"
base="80b3435558e67850c9cba4215ca81456721ef0db"
cd "$root"
git checkout "$base" -- docs/backlog.md scripts/test-baseline.ps1 server/routers/products.py
git rm -f --ignore-unmatch \
  tests/test_product_change_bind.py \
  tests/test_product_change_bind_oracle.py \
  docs/tasks/PDD-PRODUCT-CHANGE-BIND-HOTFIX-001.md \
  docs/tasks/PDD-PRODUCT-CHANGE-BIND-HOTFIX-001-verification/DIFF_FILE.patch \
  docs/tasks/PDD-PRODUCT-CHANGE-BIND-HOTFIX-001-verification/MODIFIED_FILE \
  docs/tasks/PDD-PRODUCT-CHANGE-BIND-HOTFIX-001-verification/VERIFICATION.txt \
  docs/tasks/PDD-PRODUCT-CHANGE-BIND-HOTFIX-001-verification/ROLLBACK.sh
printf 'ROLLBACK_RESULT=PASS\n'
