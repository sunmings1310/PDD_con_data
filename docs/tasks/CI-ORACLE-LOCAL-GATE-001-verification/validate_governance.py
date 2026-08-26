#!/usr/bin/env python3
"""Static governance checks for CI-ORACLE-LOCAL-GATE-001."""

from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys

import yaml


ROOT = pathlib.Path(__file__).resolve().parents[3]
BASE = "origin/main"
ALLOWED_PREFIXES = (
    ".github/",
    "docs/",
)
ALLOWED_ROOT = {"WORKFLOW.md"}
FORBIDDEN_WORKFLOW_TOKENS = (
    "secrets.T003_ORACLE_",
    "secrets.TEST_JWT_SECRET",
    "oracle-integration:",
    "oracledb.connect",
)


def run(*args: str) -> str:
    result = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(args)}\n{result.stderr}")
    return result.stdout


def check_yaml() -> None:
    paths = sorted((ROOT / ".github/workflows").glob("*.yml"))
    for path in paths:
        yaml.safe_load(path.read_text(encoding="utf-8"))
    print(f"YAML_PARSE=PASS files={len(paths)}")


def check_ci() -> None:
    path = ROOT / ".github/workflows/ci.yml"
    text = path.read_text(encoding="utf-8")
    scope_text = (ROOT / ".github/scripts/classify_oracle_scope.py").read_text(encoding="utf-8")
    doc = yaml.safe_load(text)
    jobs = set(doc["jobs"])
    expected = {"governance", "python-offline", "web-build", "android-jvm", "oracle-scope", "oracle-local-evidence"}
    if jobs != expected:
        raise AssertionError(f"unexpected CI jobs: {sorted(jobs)}")
    for token in FORBIDDEN_WORKFLOW_TOKENS:
        if token in text:
            raise AssertionError(f"hosted database/secret token remains: {token}")
    required = (
        "Oracle local evidence gate",
        "validate_oracle_local_evidence.py",
        "github.event.pull_request.head.sha",
        "classify_oracle_scope.py",
    )
    for token in required:
        if token not in text:
            raise AssertionError(f"required CI semantic missing: {token}")
    if "ORACLE_CI_MODE=not_required" in text or 'ORACLE_CI_MODE" == "not_required' in text:
        raise AssertionError("repository variable must not bypass Oracle-sensitive classification")
    for token in ("scripts/test-baseline.ps1", "tests/test_phase2_schema_contract.py", "tests/test_job_service.py"):
        if token not in scope_text:
            raise AssertionError(f"canonical Oracle scope token missing: {token}")
    print("CI_STATIC=PASS hosted_db_access=absent oracle_bypass=absent")


def check_markdown() -> None:
    files = list(ROOT.glob("*.md")) + list((ROOT / "docs").rglob("*.md")) + list((ROOT / ".github").glob("*.md"))
    pattern = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
    failures = []
    for source in sorted(set(files)):
        for raw in pattern.findall(source.read_text(encoding="utf-8")):
            target = raw.strip().split()[0].strip("<>")
            if not target or target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            target_path = (source.parent / target.split("#", 1)[0]).resolve()
            if not target_path.exists():
                failures.append(f"{source.relative_to(ROOT)} -> {target}")
    if failures:
        raise AssertionError("missing Markdown links:\n" + "\n".join(failures))
    print(f"MARKDOWN_LINKS=PASS files={len(set(files))}")


def check_scope() -> None:
    changed = [line for line in run("git", "diff", "--name-only", f"{BASE}...HEAD").splitlines() if line]
    forbidden = [path for path in changed if path not in ALLOWED_ROOT and not path.startswith(ALLOWED_PREFIXES)]
    if forbidden:
        raise AssertionError(f"out-of-scope paths: {forbidden}")
    business = [path for path in changed if path.startswith(("server/", "migrations/", "android_collector/", "web/src/", "tests/"))]
    if business:
        raise AssertionError(f"business/schema/test paths changed: {business}")
    print(f"SCOPE_STATIC=PASS changed_files={len(changed)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", choices=("all", "yaml", "ci", "markdown", "scope"), default="all")
    args = parser.parse_args()
    checks = {"yaml": check_yaml, "ci": check_ci, "markdown": check_markdown, "scope": check_scope}
    try:
        selected = checks.values() if args.check == "all" else (checks[args.check],)
        for check in selected:
            check()
    except (AssertionError, RuntimeError, OSError, yaml.YAMLError) as exc:
        print(f"GOVERNANCE_VALIDATION=FAIL: {exc}", file=sys.stderr)
        return 1
    print("GOVERNANCE_VALIDATION=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
