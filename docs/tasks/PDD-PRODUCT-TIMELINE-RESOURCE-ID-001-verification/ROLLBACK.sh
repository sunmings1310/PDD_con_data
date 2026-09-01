#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 <modified-copy-git-repository>" >&2
  exit 64
fi

repo="$1"
script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
patch="$script_dir/DIFF_FILE.patch"
git -C "$repo" apply --unidiff-zero --reverse --check "$patch"
git -C "$repo" apply --unidiff-zero --reverse "$patch"
git -C "$repo" diff --check
git -C "$repo" diff --quiet
echo "ROLLBACK_RESULT=PASS"