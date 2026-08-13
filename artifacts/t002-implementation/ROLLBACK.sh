#!/bin/sh
set -eu
target="${1:?usage: ROLLBACK.sh PATH EXPECTED_SHA256}"
expected="${2:?usage: ROLLBACK.sh PATH EXPECTED_SHA256}"
actual="$(sha256sum "$target" | awk '{print toupper($1)}')"
[ "$actual" = "$expected" ] || { echo "ROLLBACK_REFUSED hash_mismatch"; exit 2; }
rm -- "$target"
echo "ROLLBACK_OK restored_status=ABSENT"