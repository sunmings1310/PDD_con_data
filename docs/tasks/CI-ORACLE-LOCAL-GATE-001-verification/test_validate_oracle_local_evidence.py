from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
VALIDATOR_PATH = ROOT / ".github/scripts/validate_oracle_local_evidence.py"
SPEC = importlib.util.spec_from_file_location("oracle_evidence", VALIDATOR_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)
NOW = dt.datetime(2026, 8, 25, 4, 0, tzinfo=dt.timezone.utc)
HEAD = "a" * 40


class OracleEvidenceValidatorTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        artifacts = []
        for role, name in (
            ("modified_file", "MODIFIED_FILE.txt"),
            ("diff_file", "DIFF_FILE.patch"),
            ("verification", "VERIFICATION.txt"),
            ("rollback", "ROLLBACK.sh"),
        ):
            path = self.root / name
            path.write_text(f"{role}\n", encoding="utf-8")
            if role == "rollback":
                subprocess.run(["git", "add", "--chmod=+x", name], cwd=self.root, check=True)
            else:
                subprocess.run(["git", "add", name], cwd=self.root, check=True)
            artifacts.append({"role": role, "path": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        literal = "Ran 46 tests in 12.000s\n\nOK\n[PASS] oracle-integration: exit=0\nSUMMARY PASS=1 FAIL=0 BLOCKED=0 STRICT=True"
        self.manifest = {
            "schema_version": 1,
            "head_sha": HEAD,
            "generated_at": "2026-08-25T03:30:00Z",
            "command": MODULE.CANONICAL_COMMAND,
            "status": "PASS",
            "exit_code": 0,
            "environment": {"identifier": "oracle-free-local-01", "isolation": "local-isolated-oracle", "database": "Oracle", "persistent_business_changes": False},
            "test_run": {"suite": "oracle-integration", "tests_total": 46, "passed": 46, "failures": 0, "errors": 0, "skipped": 0, "blocked": 0},
            "literal_output": literal,
            "literal_output_sha256": hashlib.sha256(literal.encode()).hexdigest(),
            "rollback": {"status": "PASS", "command": "bash ROLLBACK.sh copy", "literal_result": "ROLLBACK=PASS restored", "exit_code": 0, "persistent_business_changes": False},
            "artifacts": artifacts,
            "trust_boundary": "GitHub validates structure and hashes; Independent Reviewer verifies the local Oracle run provenance.",
        }

    def tearDown(self):
        self.temp.cleanup()

    def validate(self, manifest=None, head=HEAD, now=NOW):
        MODULE.validate_manifest(manifest or self.manifest, head, self.root, now, 72)

    def test_valid_evidence(self):
        self.validate()

    def test_wrong_head(self):
        with self.assertRaisesRegex(MODULE.EvidenceError, "Head SHA"):
            self.validate(head="b" * 40)

    def test_missing_field(self):
        del self.manifest["environment"]
        with self.assertRaisesRegex(MODULE.EvidenceError, "missing fields"):
            self.validate()

    def test_nonzero_exit(self):
        self.manifest["exit_code"] = 1
        with self.assertRaisesRegex(MODULE.EvidenceError, "exit_code"):
            self.validate()

    def test_skipped_or_blocked(self):
        for status in ("SKIPPED", "BLOCKED"):
            with self.subTest(status=status):
                self.manifest["status"] = status
                with self.assertRaisesRegex(MODULE.EvidenceError, "must be PASS"):
                    self.validate()
        self.manifest["status"] = "PASS"

    def test_tampered_literal_result(self):
        self.manifest["literal_output"] += "\ntampered"
        with self.assertRaisesRegex(MODULE.EvidenceError, "hash mismatch"):
            self.validate()

    def test_expired_evidence(self):
        with self.assertRaisesRegex(MODULE.EvidenceError, "expired"):
            self.validate(now=NOW + dt.timedelta(hours=73))

    def test_wrong_command(self):
        self.manifest["command"] = "python -m unittest"
        with self.assertRaisesRegex(MODULE.EvidenceError, "canonical"):
            self.validate()

    def test_artifact_tamper(self):
        (self.root / "VERIFICATION.txt").write_text("changed\n", encoding="utf-8")
        with self.assertRaisesRegex(MODULE.EvidenceError, "artifact hash mismatch"):
            self.validate()

    def test_pr_body_extraction(self):
        body = f"before\n{MODULE.MARKER}\n```json\n{json.dumps(self.manifest)}\n```\nafter"
        self.assertEqual(MODULE.extract_manifest(body)["head_sha"], HEAD)


if __name__ == "__main__":
    unittest.main()
