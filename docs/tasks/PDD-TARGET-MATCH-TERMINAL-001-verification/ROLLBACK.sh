#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR=$(CDPATH= cd -- $(dirname -- "$0") && pwd)
REPO_ROOT=$(git -C "$SCRIPT_DIR/../../.." rev-parse --show-toplevel)
PATCH=$SCRIPT_DIR/DIFF_FILE.patch
BASE=80b3435558e67850c9cba4215ca81456721ef0db
git -C "$REPO_ROOT" apply -R --check --unidiff-zero --whitespace=nowarn "$PATCH"
git -C "$REPO_ROOT" apply -R --unidiff-zero --whitespace=nowarn "$PATCH"
git -C "$REPO_ROOT" checkout "$BASE" -- docs/backlog.md
git -C "$REPO_ROOT" rm -rf --ignore-unmatch -- docs/tasks/PDD-TARGET-MATCH-TERMINAL-001.md docs/tasks/PDD-TARGET-MATCH-TERMINAL-001-verification
