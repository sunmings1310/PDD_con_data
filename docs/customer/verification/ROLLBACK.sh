#!/usr/bin/env python3
import pathlib
import sys

target = pathlib.Path(sys.argv[1])
target.unlink(missing_ok=True)
print(f"ROLLBACK_RESULT=removed:{target}")
