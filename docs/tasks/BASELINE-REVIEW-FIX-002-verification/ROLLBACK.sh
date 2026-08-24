#!/usr/bin/env bash
set -euo pipefail

BASELINE="d290abbe4b14937462e93e9a731452c08f7d0148"
EXPECTED_SHA256="27da00a3856dcc7c551af11f0c7f8a55882ceb1ec780fcdf71bd1f0811b2d6e0"
TARGET="${1:-scripts/test-baseline.ps1}"

# The checked-out fixture was captured with Git's Windows CRLF worktree form.
git show "${BASELINE}:scripts/test-baseline.ps1" | sed 's/$/\r/' > "${TARGET}"
ACTUAL_SHA256="$(sha256sum "${TARGET}" | awk '{print $1}')"
if [[ "${ACTUAL_SHA256}" != "${EXPECTED_SHA256}" ]]; then
  printf 'ROLLBACK hash mismatch: expected=%s actual=%s\n' "${EXPECTED_SHA256}" "${ACTUAL_SHA256}" >&2
  exit 1
fi
printf 'ROLLBACK restored scripts/test-baseline.ps1 sha256=%s target=%s\n' "${ACTUAL_SHA256}" "${TARGET}"
