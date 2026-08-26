#!/usr/bin/env python3
"""Classify whether a change set requires fixed-Head local Oracle evidence."""

from __future__ import annotations

import argparse
import pathlib


CANONICAL_TEST_FILES = {
    "tests/test_task_state_r2_oracle.py",
    "tests/test_phase2_schema_contract.py",
    "tests/test_job_service.py",
    "tests/test_job_reconciliation_oracle_integration.py",
    "tests/test_phase2_route_oracle.py",
    "tests/test_phase3_oracle.py",
    "tests/test_phase5_oracle.py",
    "tests/test_phase55_oracle.py",
    "tests/test_phase6a_oracle.py",
}


def is_oracle_sensitive(path: str) -> bool:
    normalized = path.replace("\\", "/")
    name = normalized.rsplit("/", 1)[-1]
    return (
        (normalized.startswith("server/") and normalized.endswith(".py"))
        or normalized == "scripts/test-baseline.ps1"
        or (normalized.startswith("scripts/") and name.startswith("migrate") and normalized.endswith(".py"))
        or normalized.startswith("migrations/")
        or normalized in CANONICAL_TEST_FILES
        or (normalized.startswith("tests/") and "oracle" in name.lower() and normalized.endswith(".py"))
    )


def classify(paths: list[str]) -> tuple[bool, str]:
    matched = sorted(path for path in paths if is_oracle_sensitive(path))
    if matched:
        return True, "Oracle-sensitive file changed: " + matched[0]
    return False, "no Oracle-sensitive file changed"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--github-output", type=pathlib.Path)
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args()
    required, reason = classify(args.paths)
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as handle:
            handle.write(f"required={'true' if required else 'false'}\nreason={reason}\n")
    if required:
        print(f"ORACLE_GATE=REQUIRED: {reason}")
    else:
        print("ORACLE_GATE=SKIPPED: explicitly not applicable to this change set")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
