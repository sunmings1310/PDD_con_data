#!/usr/bin/env sh
set -eu

target="${1:-.}"
root="$(cd "$target" && git rev-parse --show-toplevel)"
root="$(cd "$root" && pwd -P)"
artifact_rel="docs/tasks/BL-110-WS-TENANT-BOUNDARY-verification"
artifact_dir="$root/$artifact_rel"
script_dir="$(cd "$(dirname "$0")" && pwd -P)"
patch_file="$script_dir/DIFF_FILE.patch"

if [ "$script_dir" != "$artifact_dir" ]; then
  echo "ROLLBACK_REJECTED=artifact_path_mismatch" >&2
  exit 2
fi
if [ ! -f "$patch_file" ]; then
  echo "ROLLBACK_REJECTED=diff_missing" >&2
  exit 3
fi

git -C "$root" apply --unidiff-zero --reverse --check "$patch_file"
git -C "$root" apply --unidiff-zero --reverse "$patch_file"

# The resolved path was checked above and is confined to the target repository.
rm -rf -- "$artifact_dir"

echo "ROLLBACK_APPLIED=TRUE"
echo "RESTORED_BASE=origin/main"
