"""Run the offline Python suite without the separately gated Oracle integration suite."""

from __future__ import annotations

import pathlib
import sys
import unittest
import importlib.util


INTEGRATION_MODULE = "test_task_state_r2_oracle"


def main() -> int:
    root = pathlib.Path(__file__).resolve().parents[1]
    tests_dir = root / "tests"
    sys.path.insert(0, str(root))
    suite = unittest.TestSuite()
    for test_path in sorted(tests_dir.glob("test_*.py")):
        if test_path.stem == INTEGRATION_MODULE:
            continue
        spec = importlib.util.spec_from_file_location(test_path.stem, test_path)
        assert spec and spec.loader, test_path
        module = importlib.util.module_from_spec(spec)
        sys.modules[test_path.stem] = module
        spec.loader.exec_module(module)
        suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
