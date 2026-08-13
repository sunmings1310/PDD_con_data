#!/bin/sh
set -eu
target="${1:?usage: ROLLBACK.sh PATH}"
expected="${2:?usage: ROLLBACK.sh PATH EXPECTED_SHA256}"
actual="$(sha256sum "$target" | awk '{print toupper($1)}')"
if [ "$actual" != "$expected" ]; then
  echo "ROLLBACK_REFUSED hash_mismatch actual=$actual"
  exit 2
fi
rm -- "$target"
echo "ROLLBACK_OK restored_status=ABSENT"