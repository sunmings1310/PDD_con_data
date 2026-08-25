#!/usr/bin/env python3
"""Validate PR-scoped evidence for the local isolated Oracle strict gate."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re
import subprocess
import sys
from typing import Any


SCHEMA_VERSION = 1
CANONICAL_COMMAND = (
    r"powershell -NoProfile -File .\scripts\test-baseline.ps1 -Suite oracle -Strict"
)
MARKER = "<!-- oracle-local-evidence:v1 -->"
ROLES = {"modified_file", "diff_file", "verification", "rollback"}
EXPECTED_TEST_FILES = [
    "tests/test_task_state_r2_oracle.py",
    "tests/test_phase2_schema_contract.py",
    "tests/test_job_service.py",
    "tests/test_job_reconciliation_oracle_integration.py",
    "tests/test_phase2_route_oracle.py",
    "tests/test_phase3_oracle.py",
    "tests/test_phase5_oracle.py",
    "tests/test_phase55_oracle.py",
    "tests/test_phase6a_oracle.py",
]
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")


class EvidenceError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


def _parse_time(value: Any) -> dt.datetime:
    _require(isinstance(value, str), "generated_at must be an ISO-8601 string")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceError("generated_at is not valid ISO-8601") from exc
    _require(parsed.tzinfo is not None, "generated_at must include a timezone")
    return parsed.astimezone(dt.timezone.utc)


def extract_manifest(pr_body: str) -> dict[str, Any]:
    _require(pr_body.count(MARKER) == 1, "PR body must contain exactly one evidence marker")
    tail = pr_body.split(MARKER, 1)[1]
    match = re.search(r"```json\s*(\{.*?\})\s*```", tail, re.DOTALL)
    _require(match is not None, "evidence marker must be followed by a JSON code block")
    try:
        value = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise EvidenceError(f"evidence JSON is invalid: {exc.msg}") from exc
    _require(isinstance(value, dict), "evidence JSON must be an object")
    return value


def _sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_mode(root: pathlib.Path, relative: str) -> str:
    result = subprocess.run(
        ["git", "ls-files", "--stage", "--", relative],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    _require(result.returncode == 0 and result.stdout.strip(), f"artifact is not tracked: {relative}")
    return result.stdout.split(None, 1)[0]


def validate_manifest(
    manifest: dict[str, Any],
    expected_head: str,
    root: pathlib.Path,
    now: dt.datetime,
    max_age_hours: int,
) -> None:
    required = {
        "schema_version", "head_sha", "generated_at", "command", "status",
        "exit_code", "environment", "test_run", "literal_output",
        "literal_output_sha256", "rollback", "artifacts", "trust_boundary",
    }
    _require(required <= manifest.keys(), f"missing fields: {sorted(required - manifest.keys())}")
    _require(manifest["schema_version"] == SCHEMA_VERSION, "unsupported schema_version")
    _require(isinstance(expected_head, str) and SHA_RE.fullmatch(expected_head) is not None, "expected Head SHA is invalid")
    _require(manifest["head_sha"] == expected_head, "evidence Head SHA does not match PR Head")
    _require(manifest["command"] == CANONICAL_COMMAND, "command is not the canonical Oracle strict command")
    _require(manifest["status"] == "PASS", "Oracle evidence status must be PASS")
    _require(manifest["exit_code"] == 0, "Oracle strict command exit_code must be 0")

    generated = _parse_time(manifest["generated_at"])
    _require(generated <= now + dt.timedelta(minutes=5), "evidence timestamp is in the future")
    _require(now - generated <= dt.timedelta(hours=max_age_hours), "evidence is expired")

    environment = manifest["environment"]
    _require(isinstance(environment, dict), "environment must be an object")
    _require(isinstance(environment.get("identifier"), str) and environment["identifier"].strip(), "environment.identifier is required")
    _require(environment.get("isolation") == "local-isolated-oracle", "environment must identify local isolated Oracle")
    _require(environment.get("database") == "Oracle", "environment.database must be Oracle")
    _require(environment.get("persistent_business_changes") is False, "persistent business changes must be false")

    run = manifest["test_run"]
    _require(isinstance(run, dict), "test_run must be an object")
    for field in ("tests_total", "passed", "failures", "errors", "skipped", "blocked"):
        _require(type(run.get(field)) is int and run[field] >= 0, f"test_run.{field} must be a non-negative integer")
    _require(run.get("suite") == "oracle-integration", "test_run.suite must be oracle-integration")
    _require(run.get("test_files") == EXPECTED_TEST_FILES, "test_run.test_files does not match the canonical Oracle strict collection")
    _require(run["tests_total"] > 0, "tests_total must be positive")
    _require(run["passed"] == run["tests_total"], "every Oracle test must pass")
    _require(run["failures"] == run["errors"] == run["skipped"] == run["blocked"] == 0, "failures/errors/skipped/blocked must all be zero")

    literal = manifest["literal_output"]
    _require(isinstance(literal, str) and literal.strip(), "literal_output is required")
    digest = hashlib.sha256(literal.encode("utf-8")).hexdigest()
    _require(HASH_RE.fullmatch(str(manifest["literal_output_sha256"])) is not None, "literal_output_sha256 is invalid")
    _require(digest == manifest["literal_output_sha256"], "literal_output hash mismatch")
    _require(re.search(rf"Ran\s+{run['tests_total']}\s+tests?\b", literal) is not None, "literal_output test count mismatch")
    _require(re.search(r"^OK\s*$", literal, re.MULTILINE) is not None, "literal_output does not contain unittest OK")
    _require("[PASS] oracle-integration: exit=0" in literal, "literal_output lacks Oracle PASS result")
    _require("SUMMARY PASS=1 FAIL=0 BLOCKED=0 STRICT=True" in literal, "literal_output lacks strict PASS summary")
    _require(
        re.search(r"^\[(?:SKIPPED|BLOCKED|FAIL)\]", literal, re.MULTILINE) is None,
        "literal_output contains a non-PASS gate result",
    )

    rollback = manifest["rollback"]
    _require(isinstance(rollback, dict), "rollback must be an object")
    _require(rollback.get("status") == "PASS", "rollback status must be PASS")
    _require(rollback.get("exit_code") == 0, "rollback exit_code must be 0")
    _require(isinstance(rollback.get("command"), str) and rollback["command"].strip(), "rollback command is required")
    _require(isinstance(rollback.get("literal_result"), str) and rollback["literal_result"].strip(), "rollback literal_result is required")
    _require(rollback.get("persistent_business_changes") is False, "rollback must confirm no persistent business changes")

    artifacts = manifest["artifacts"]
    _require(isinstance(artifacts, list) and len(artifacts) == 4, "exactly four verification artifacts are required")
    seen: set[str] = set()
    root = root.resolve()
    for artifact in artifacts:
        _require(isinstance(artifact, dict), "each artifact must be an object")
        role, relative, expected_hash = artifact.get("role"), artifact.get("path"), artifact.get("sha256")
        _require(role in ROLES and role not in seen, "artifact roles must be unique and complete")
        _require(isinstance(relative, str) and relative, "artifact.path is required")
        _require(HASH_RE.fullmatch(str(expected_hash)) is not None, "artifact.sha256 is invalid")
        path = (root / relative).resolve()
        _require(path == root or root in path.parents, "artifact path escapes repository")
        _require(path.is_file(), f"artifact does not exist: {relative}")
        _require(_sha256(path) == expected_hash, f"artifact hash mismatch: {relative}")
        if role == "rollback":
            _require(_git_mode(root, relative) == "100755", "rollback artifact must be executable in git")
        seen.add(role)
    _require(seen == ROLES, "all four artifact roles are required")
    _require(isinstance(manifest["trust_boundary"], str) and "Reviewer" in manifest["trust_boundary"], "trust_boundary must name the Reviewer trust boundary")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, help="JSON manifest or PR body file")
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--repository", default=".")
    parser.add_argument("--from-pr-body", action="store_true")
    parser.add_argument("--now", help="ISO-8601 time for deterministic tests")
    parser.add_argument("--max-age-hours", type=int, default=72)
    args = parser.parse_args()
    try:
        raw = pathlib.Path(args.manifest).read_text(encoding="utf-8")
        manifest = extract_manifest(raw) if args.from_pr_body else json.loads(raw)
        now = _parse_time(args.now) if args.now else dt.datetime.now(dt.timezone.utc)
        validate_manifest(manifest, args.expected_head.lower(), pathlib.Path(args.repository), now, args.max_age_hours)
    except (EvidenceError, json.JSONDecodeError, OSError) as exc:
        print(f"ORACLE_LOCAL_EVIDENCE=FAIL: {exc}", file=sys.stderr)
        return 2
    print(f"ORACLE_LOCAL_EVIDENCE=PASS head={args.expected_head.lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
