#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
TARGET="${1:?usage: ROLLBACK.sh TARGET_COPY}"
git -C "$ROOT" show 90b53658af5bf1e1f0488aaeb520e59887c8c91b:android_collector/app/src/main/java/com/collector/pdd/collector/PddCollector.kt > "$TARGET"
