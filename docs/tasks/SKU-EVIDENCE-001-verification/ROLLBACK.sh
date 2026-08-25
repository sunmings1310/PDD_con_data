#!/usr/bin/env python3
from __future__ import annotations

import hashlib
from pathlib import Path
import sys


EXPECTED_SHA256 = "aed6320bfca34b41e4f3332e2d84d09d78ee3c9b14fd3d6b850cbf9ccabfbe21"


def main() -> int:
    if len(sys.argv) != 2:
        print("ROLLBACK_RESULT=FAIL")
        print("ROLLBACK_REASON=usage: ROLLBACK.sh <copy-of-MODIFIED_FILE.txt>")
        print("ROLLBACK_EXIT=2")
        return 2

    target = Path(sys.argv[1])
    if not target.is_file():
        print("ROLLBACK_RESULT=FAIL")
        print("ROLLBACK_REASON=target-not-found")
        print("ROLLBACK_EXIT=2")
        return 2

    data = target.read_bytes()
    old = b"REAL_DEVICE_GATE=BLOCKED\n"
    new = b"REAL_DEVICE_GATE=PENDING\n"
    if data != old:
        print("ROLLBACK_RESULT=FAIL")
        print("ROLLBACK_REASON=unexpected-modified-fixture")
        print("ROLLBACK_EXIT=2")
        return 2
    target.write_bytes(new)
    restored = hashlib.sha256(target.read_bytes()).hexdigest()

    print(f"ROLLBACK_TARGET={target}")
    print(f"RESTORED_SHA256={restored}")
    print(f"EXPECTED_SHA256={EXPECTED_SHA256}")
    print(f"ROLLBACK_MATCH={'true' if restored == EXPECTED_SHA256 else 'false'}")
    print(f"ROLLBACK_RESULT={'PASS' if restored == EXPECTED_SHA256 else 'FAIL'}")
    print(f"ROLLBACK_EXIT={0 if restored == EXPECTED_SHA256 else 2}")
    return 0 if restored == EXPECTED_SHA256 else 2


if __name__ == "__main__":
    raise SystemExit(main())
