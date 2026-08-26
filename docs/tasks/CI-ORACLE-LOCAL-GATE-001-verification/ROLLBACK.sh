#!/usr/bin/env python3
"""Reverse the workflow-only governance patch in a disposable repository copy."""

from __future__ import annotations

import hashlib
import pathlib
import subprocess
import sys


ORIGINAL_SHA256 = "65f047b203895d912309fa94a2b7eb7fb860630f2529c795096f18b2604f3c8b"
MODIFIED_SHA256 = "6b31ac1d29f92877dfa0c35b41e9de91284c77857c98486c5c32c31c0fda5278"


def digest(path: pathlib.Path) -> str:
    # Git for Windows may materialize CRLF while the committed blob is LF.
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: ROLLBACK.sh <disposable-repository-copy>", file=sys.stderr)
        return 2
    target = pathlib.Path(sys.argv[1]).resolve()
    workflow = target / ".github/workflows/ci.yml"
    patch = pathlib.Path(__file__).with_name("DIFF_FILE.patch").resolve()
    if not workflow.is_file() or digest(workflow) != MODIFIED_SHA256:
        print("ROLLBACK=FAIL input is not the verified modified workflow", file=sys.stderr)
        return 2
    result = subprocess.run(
        [
            "git", "apply", "--reverse", "--unidiff-zero",
            "--ignore-space-change", "--whitespace=nowarn", str(patch),
        ],
        cwd=target,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        print(f"ROLLBACK=FAIL git apply exit={result.returncode}: {result.stderr.strip()}", file=sys.stderr)
        return result.returncode
    restored = digest(workflow)
    text = workflow.read_text(encoding="utf-8")
    if restored != ORIGINAL_SHA256:
        print(f"ROLLBACK=FAIL restored_sha256={restored}", file=sys.stderr)
        return 1
    if "oracle-integration:" not in text or "secrets.T003_ORACLE_HOST" not in text or "oracle-local-evidence:" in text:
        print("ROLLBACK=FAIL restored workflow behavior does not match baseline", file=sys.stderr)
        return 1
    print(f"ROLLBACK=PASS restored_sha256={restored} hosted_oracle_job=restored local_evidence_job=absent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
