#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
TARGET="${1:?usage: ROLLBACK.sh TARGET_COPY}"
BASELINE="246f18114c6ab647051229a186c33e76d2fbe671"
git -C "$ROOT" show "$BASELINE:server/raw_capture.py" > "$TARGET"
ACTUAL="$(sha256sum "$TARGET" | awk '{print $1}')"
EXPECTED="052497f29254e20fe06cf580cfc822bdb4413b50d55d64df0db382b438d8a1e5"
printf 'RESTORED_SHA256=%s\n' "$ACTUAL"
if [[ "$ACTUAL" != "$EXPECTED" ]]; then
  printf 'RESTORED_MATCH=False\n'
  exit 1
fi
printf 'RESTORED_MATCH=True\n'
