#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: ROLLBACK.sh <probe-root> <base-sha>" >&2
  exit 64
fi

probe_root="$1"
base_sha="$2"

git -C "$probe_root" cat-file -e "${base_sha}^{commit}"
git -C "$probe_root" checkout "$base_sha" -- \
  PRODUCT.md \
  WORKFLOW.md \
  docs/CURRENT_STATE.md \
  docs/backlog.md \
  docs/roadmap.md \
  docs/product/feature-list.md \
  docs/product/feature-list-summary.md \
  docs/tasks/TEMPLATE.md

rm -f "$probe_root/docs/tasks/PRODUCT-REQUIREMENTS-BASELINE-001.md"
rm -rf "$probe_root/docs/tasks/PRODUCT-REQUIREMENTS-BASELINE-001-verification"

restored_sha256="$(git -C "$probe_root" hash-object PRODUCT.md)"
expected_blob="$(git -C "$probe_root" rev-parse "${base_sha}:PRODUCT.md")"
if [[ "$restored_sha256" != "$expected_blob" ]]; then
  echo "ROLLBACK_MATCH=false"
  exit 1
fi

echo "RESTORED_BLOB=$restored_sha256"
echo "ROLLBACK_MATCH=true"
echo "ROLLBACK_RESULT=restored"
