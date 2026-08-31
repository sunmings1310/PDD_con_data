#!/usr/bin/env bash
set -euo pipefail
BASE=e15f50f93ee91d613011eed36324c14753ef4025
REPO_ROOT=$(git rev-parse --show-toplevel)
PATCH=$(mktemp)
trap 'rm -f "$PATCH"' EXIT
git -C "$REPO_ROOT" diff --binary "$BASE" HEAD > "$PATCH"
git -C "$REPO_ROOT" apply -R --whitespace=nowarn "$PATCH"
git -C "$REPO_ROOT" diff --exit-code "$BASE" -- .
printf 'RESTORED_DIFF_VS_BASE_EXIT=0\n'
printf 'TASK_PRESENT=%s\n' "$(test -e "$REPO_ROOT/docs/tasks/PDD-COLLECTION-OBSERVABILITY-001.md" && echo true || echo false)"
printf 'VERIFICATION_PRESENT=%s\n' "$(test -e "$REPO_ROOT/docs/tasks/PDD-COLLECTION-OBSERVABILITY-001-verification/VERIFICATION.txt" && echo true || echo false)"