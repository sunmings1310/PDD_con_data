"""Offline contract tests for the Phase 2 additive Oracle scheduler schema."""

from __future__ import annotations

import os
from pathlib import Path
import re
import unittest

import oracledb


ROOT = Path(__file__).resolve().parents[1]
INIT_SCHEMA = (ROOT / "server" / "init_schema.py").read_text(encoding="utf-8")
MIGRATE = (ROOT / "server" / "migrate.py").read_text(encoding="utf-8")
ORACLE_REQUIRED = ("T003_ORACLE_DSN", "T003_ORACLE_USER", "T003_ORACLE_PASSWORD")
ORACLE_SCHEMA_ENABLED = os.getenv("T003_ORACLE_TEST_ENABLED") == "1" and all(
    os.getenv(name) for name in ORACLE_REQUIRED
)


class Phase2SchemaContractTests(unittest.TestCase):
    def test_canonical_tables_and_sequences_are_declared(self) -> None:
        tables = {
            "SJZQ_COLLECTION_JOB",
            "SJZQ_COLLECTION_ATTEMPT",
            "SJZQ_COLLECTION_LEASE",
            "SJZQ_COLLECTION_CHECKPOINT",
            "SJZQ_COLLECTION_OUTBOX",
            "SJZQ_JOB_EVENT",
        }
        sequences = {
            "SJZQ_SEQ_COLLECTION_JOB",
            "SJZQ_SEQ_COLLECTION_ATTEMPT",
            "SJZQ_SEQ_COLLECTION_LEASE",
            "SJZQ_SEQ_COLLECTION_CHECKPOINT",
            "SJZQ_SEQ_COLLECTION_OUTBOX",
            "SJZQ_SEQ_JOB_EVENT",
        }
        for name in tables | sequences:
            self.assertIn(name, INIT_SCHEMA)
            self.assertIn(name, MIGRATE)

    def test_task_pause_deadline_and_device_execution_pointers_are_additive(self) -> None:
        for name in ("PAUSE_STATE", "PAUSE_REQUESTED", "DEADLINE_AT", "PAUSED_AT"):
            self.assertIn(name, INIT_SCHEMA)
            self.assertIn(name, MIGRATE)
        for name in ("ACTIVE_JOB_ID", "ACTIVE_ATTEMPT_ID"):
            self.assertIn(name, INIT_SCHEMA)
            self.assertIn(name, MIGRATE)
        self.assertIn("DEFAULT 'active' NOT NULL", INIT_SCHEMA)
        self.assertIn("PAUSE_STATE IN ('active', 'paused')", INIT_SCHEMA)

    def test_job_has_stable_identity_lease_checkpoint_and_result_columns(self) -> None:
        for name in (
            "JOB_KEY",
            "ACTIVE_ATTEMPT_ID",
            "LEASE_TOKEN_HASH",
            "LEASE_EXPIRES_AT",
            "PAUSE_REQUESTED",
            "CHECKPOINT_VERSION",
            "CHECKPOINT_JSON",
            "RESULT_RECEIPT_KEY",
            "RESULT_PRODUCT_ID",
            "DEVICE_ID",
        ):
            self.assertIn(name, INIT_SCHEMA)
        self.assertIn("UK_SJZQ_COLLECTION_JOB_KEY UNIQUE (JOB_KEY)", INIT_SCHEMA)

    def test_attempt_and_lease_store_hashes_not_bearer_tokens(self) -> None:
        for table in ("SJZQ_COLLECTION_ATTEMPT", "SJZQ_COLLECTION_LEASE"):
            start = INIT_SCHEMA.index(f"CREATE TABLE {table}")
            end = INIT_SCHEMA.index('"""', start + 1)
            ddl = INIT_SCHEMA[start:end]
            self.assertIn("LEASE_TOKEN_HASH", ddl)
            self.assertNotRegex(ddl, r"\bLEASE_TOKEN\s+VARCHAR2")
        self.assertIn("hash the supplied token before comparison", MIGRATE)

    def test_status_checks_and_idempotency_constraints_exist(self) -> None:
        for status in (
            "'pending'", "'leased'", "'running'", "'paused'", "'retry_wait'",
            "'success'", "'failed'", "'cancelled'", "'dead'", "'quarantined'",
        ):
            self.assertIn(status, INIT_SCHEMA)
        for fragment in (
            "UK_SJZQ_ATTEMPT_NO UNIQUE (JOB_ID, ATTEMPT_NO)",
            "UK_SJZQ_CKPT_JOB_VER UNIQUE (JOB_ID, VERSION)",
            "UK_SJZQ_CKPT_JOB_IDEM UNIQUE (JOB_ID, IDEMPOTENCY_KEY)",
            "UK_SJZQ_OUTBOX_EVENT UNIQUE (EVENT_KEY)",
            "UK_SJZQ_JOB_EVENT_KEY UNIQUE (EVENT_KEY)",
        ):
            self.assertIn(fragment, INIT_SCHEMA)

    def test_migration_is_idempotent_and_indexes_reclaim_paths(self) -> None:
        self.assertIn("def _ensure_phase2_job_schema", MIGRATE)
        self.assertIn("_ensure_phase2_job_schema(cur)", MIGRATE)
        self.assertIn("def _ensure_table", MIGRATE)
        self.assertIn("def _ensure_index", MIGRATE)
        self.assertIn("def _ensure_constraint", MIGRATE)
        phase2 = MIGRATE[MIGRATE.index("def _ensure_phase2_job_schema"):]
        self.assertNotIn("DROP TABLE", phase2)
        for index in (
            "IDX_SJZQ_JOB_ACQUIRE",
            "IDX_SJZQ_JOB_LEASE_EXPIRES",
            "IDX_SJZQ_ATTEMPT_EXPIRES",
            "UQ_SJZQ_ATTEMPT_ACTIVE_JOB",
            "UQ_SJZQ_ATTEMPT_ACTIVE_DEVICE",
            "IDX_SJZQ_LEASE_EXPIRES",
            "IDX_SJZQ_OUTBOX_DELIVERY",
        ):
            self.assertIn(index, phase2)

    def test_oracle_identifiers_remain_portable(self) -> None:
        names = re.findall(r"CONSTRAINT\s+([A-Z0-9_]+)", INIT_SCHEMA)
        too_long = [name for name in names if len(name) > 30]
        self.assertEqual(too_long, [])


@unittest.skipUnless(ORACLE_SCHEMA_ENABLED, "isolated Oracle schema not configured")
class Phase2OracleSchemaContractTests(unittest.TestCase):
    """Real Oracle checks for the parts source inspection cannot prove."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.connection = oracledb.connect(
            dsn=os.environ["T003_ORACLE_DSN"],
            user=os.environ["T003_ORACLE_USER"],
            password=os.environ["T003_ORACLE_PASSWORD"],
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.connection.close()

    def _next_id(self, sequence: str) -> int:
        cur = self.connection.cursor()
        try:
            cur.execute(f"SELECT {sequence}.NEXTVAL FROM DUAL")
            return int(cur.fetchone()[0])
        finally:
            cur.close()

    def test_schema_objects_and_lease_fences_exist(self) -> None:
        cur = self.connection.cursor()
        try:
            cur.execute(
                """SELECT TABLE_NAME FROM USER_TABLES WHERE TABLE_NAME IN
                ('SJZQ_COLLECTION_JOB','SJZQ_COLLECTION_ATTEMPT','SJZQ_COLLECTION_LEASE',
                 'SJZQ_COLLECTION_CHECKPOINT','SJZQ_COLLECTION_OUTBOX','SJZQ_JOB_EVENT')"""
            )
            self.assertEqual(
                {
                    "SJZQ_COLLECTION_JOB", "SJZQ_COLLECTION_ATTEMPT", "SJZQ_COLLECTION_LEASE",
                    "SJZQ_COLLECTION_CHECKPOINT", "SJZQ_COLLECTION_OUTBOX", "SJZQ_JOB_EVENT",
                },
                {str(row[0]) for row in cur.fetchall()},
            )
            cur.execute(
                """SELECT COLUMN_NAME FROM USER_TAB_COLUMNS
                   WHERE TABLE_NAME='SJZQ_COLLECTION_JOB' AND COLUMN_NAME IN
                   ('ACTIVE_ATTEMPT_ID','LEASE_TOKEN_HASH','LEASE_EXPIRES_AT','PAUSE_REQUESTED',
                    'CHECKPOINT_VERSION','CHECKPOINT_JSON','RESULT_RECEIPT_KEY','RESULT_PRODUCT_ID','DEVICE_ID')"""
            )
            self.assertEqual(9, len(cur.fetchall()))
            cur.execute(
                """SELECT INDEX_NAME FROM USER_INDEXES WHERE INDEX_NAME IN
                   ('UQ_SJZQ_ATTEMPT_ACTIVE_JOB','UQ_SJZQ_ATTEMPT_ACTIVE_DEVICE')"""
            )
            self.assertEqual(
                {"UQ_SJZQ_ATTEMPT_ACTIVE_JOB", "UQ_SJZQ_ATTEMPT_ACTIVE_DEVICE"},
                {str(row[0]) for row in cur.fetchall()},
            )
        finally:
            cur.close()

    def test_active_attempt_fence_releases_only_after_terminal_transition(self) -> None:
        task_id = self._next_id("SJZQ_SEQ_TASK")
        device_id = self._next_id("SJZQ_SEQ_DEVICE")
        job_id = self._next_id("SJZQ_SEQ_COLLECTION_JOB")
        first_attempt = self._next_id("SJZQ_SEQ_COLLECTION_ATTEMPT")
        second_attempt = self._next_id("SJZQ_SEQ_COLLECTION_ATTEMPT")
        cur = self.connection.cursor()
        try:
            marker = f"p2-schema-{job_id}"
            cur.execute(
                """INSERT INTO SJZQ_DEVICE (DEVICE_ID, DEVICE_KEY, PLATFORM_CODE, STATUS)
                   VALUES (:id, :key, 'pinduoduo', 'offline')""",
                {"id": device_id, "key": marker},
            )
            cur.execute(
                """INSERT INTO SJZQ_TASK (TASK_ID, TASK_NAME, TASK_TYPE, PLATFORM_CODE, STATUS)
                   VALUES (:id, :name, 'collection', 'pinduoduo', 'pending')""",
                {"id": task_id, "name": marker},
            )
            cur.execute(
                """INSERT INTO SJZQ_COLLECTION_JOB
                   (JOB_ID, TASK_ID, DEVICE_ID, JOB_KEY, JOB_TYPE, STATUS)
                   VALUES (:job_id, :task_id, :device_id, :job_key, 'collect_task', 'pending')""",
                {"job_id": job_id, "task_id": task_id, "device_id": device_id,
                 "job_key": f"collect_task:phase2/{job_id}"},
            )
            self._insert_attempt(cur, first_attempt, job_id, device_id, 1, "a" * 64, "leased")
            with self.assertRaises(oracledb.IntegrityError):
                self._insert_attempt(cur, second_attempt, job_id, device_id, 2, "b" * 64, "running")
            cur.execute(
                """UPDATE SJZQ_COLLECTION_ATTEMPT
                   SET STATUS='reclaimed', FINISHED_AT=SYSTIMESTAMP
                   WHERE ATTEMPT_ID=:attempt_id""",
                {"attempt_id": first_attempt},
            )
            self._insert_attempt(cur, second_attempt, job_id, device_id, 2, "b" * 64, "leased")
        finally:
            self.connection.rollback()
            cur.close()

    @staticmethod
    def _insert_attempt(cur, attempt_id: int, job_id: int, device_id: int,
                        attempt_no: int, token_hash: str, status: str) -> None:
        cur.execute(
            """INSERT INTO SJZQ_COLLECTION_ATTEMPT
               (ATTEMPT_ID, JOB_ID, ATTEMPT_NO, DEVICE_ID, LEASE_TOKEN_HASH, TRACE_ID,
                STATUS, LEASE_EXPIRES_AT)
               VALUES (:attempt_id, :job_id, :attempt_no, :device_id, :token_hash, :trace_id,
                :status, SYSTIMESTAMP + INTERVAL '2' MINUTE)""",
            {"attempt_id": attempt_id, "job_id": job_id, "attempt_no": attempt_no,
             "device_id": device_id, "token_hash": token_hash,
             "trace_id": f"phase2-schema-{attempt_id}", "status": status},
        )


if __name__ == "__main__":
    unittest.main()
