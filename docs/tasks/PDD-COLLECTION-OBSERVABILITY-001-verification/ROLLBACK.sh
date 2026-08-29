#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(git -C "$SCRIPT_DIR/../../.." rev-parse --show-toplevel)
BASE=e15f50f93ee91d613011eed36324c14753ef4025
git -C "$REPO_ROOT" checkout "$BASE" -- docs/backlog.md
git -C "$REPO_ROOT" rm -rf --ignore-unmatch -- docs/tasks/PDD-COLLECTION-OBSERVABILITY-001.md docs/tasks/PDD-COLLECTION-OBSERVABILITY-001-verification
