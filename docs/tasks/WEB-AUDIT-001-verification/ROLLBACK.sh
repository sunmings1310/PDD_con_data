#!/usr/bin/env python3
"""Restore a supplied verification copy to the pre-audit status marker."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys


BASELINE = b"WEB_AUDIT_STATUS=IN_PROGRESS\n"
EXPECTED = "8b9e56432fcccb4612af85b4f039569164825ee0646931349dd60344ea4c83b0"


if len(sys.argv) != 2:
    print("usage: ROLLBACK.sh <verification-copy>", file=sys.stderr)
    raise SystemExit(2)

target = Path(sys.argv[1]).resolve()
target.write_bytes(BASELINE)
actual = hashlib.sha256(target.read_bytes()).hexdigest()
print(f"ROLLBACK_TARGET={target}")
print(f"RESTORED_SHA256={actual}")
print(f"EXPECTED_SHA256={EXPECTED}")
print(f"ROLLBACK_MATCH={str(actual == EXPECTED).lower()}")
print(f"ROLLBACK_RESULT={'PASS' if actual == EXPECTED else 'FAIL'}")
print(f"ROLLBACK_EXIT={0 if actual == EXPECTED else 1}")
raise SystemExit(0 if actual == EXPECTED else 1)
