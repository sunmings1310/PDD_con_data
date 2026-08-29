#!/usr/bin/env bash
set -euo pipefail
BASE=80b3435558e67850c9cba4215ca81456721ef0db
git apply -R --check --unidiff-zero --whitespace=nowarn DIFF_FILE.patch
git apply -R --unidiff-zero --whitespace=nowarn DIFF_FILE.patch
git checkout "$BASE" -- docs/backlog.md docs/tasks/PDD-TARGET-MATCH-TERMINAL-001.md docs/tasks/PDD-TARGET-MATCH-TERMINAL-001-verification
git clean -fd -- docs/tasks/PDD-TARGET-MATCH-TERMINAL-001-verification
