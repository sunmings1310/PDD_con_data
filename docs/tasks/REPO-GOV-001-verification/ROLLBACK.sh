#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
TARGET="${1:?usage: ROLLBACK.sh TARGET_COPY}"
git -C "$ROOT" show 13b4301445eda9768069a807a13d9f43cedb8e8f:AGENTS.md > "$TARGET"
