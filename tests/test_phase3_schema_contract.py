"""Offline contract tests for the Phase 3 additive data-quality schema."""

from __future__ import annotations

from pathlib import Path
import re
import unittest
from unittest.mock import patch

from server import migrate
from server.schema_migrations import (
    P3_ADDITIVE_COLUMNS,
    P3_INDEXES,
    P3_MIGRATION_CHECKSUM,
    P3_MIGRATION_ID,
    P3_SEQUENCES,
    P3_TABLES,
)


ROOT = Path(__file__).resolve().parents[1]
INIT_SCHEMA = (ROOT / "server" / "init_schema.py").read_text(encoding="utf-8")
MIGRATE = (ROOT / "server" / "migrate.py").read_text(encoding="utf-8")


class Phase3SchemaContractTests(unittest.TestCase):
    def test_all_phase3_tables_and_sequences_are_declared(self) -> None:
        self.assertEqual(
            {
                "SJZQ_SCHEMA_MIGRATION", "SJZQ_PRODUCT_MASTER", "SJZQ_RAW_COLLECTION",
                "SJZQ_PRODUCT_SNAPSHOT", "SJZQ_FIELD_PROVENANCE", "SJZQ_QUALITY_RESULT",
                "SJZQ_DATA_QUARANTINE", "SJZQ_SNAPSHOT_DIFF",
            },
            {name for name, _ in P3_TABLES},
        )
        self.assertEqual(7, len(P3_SEQUENCES))
        for name, _ in P3_TABLES:
            self.assertIn(name, INIT_SCHEMA)
            self.assertIn(name, MIGRATE)

    def test_identity_and_replay_uniqueness_are_explicit(self) -> None:
        ddl_by_table = dict(P3_TABLES)
        self.assertIn("UNIQUE (PLATFORM_CODE, PLATFORM_PRODUCT_ID)", ddl_by_table["SJZQ_PRODUCT_MASTER"])
        for table, fragment in (
            ("SJZQ_RAW_COLLECTION", "UNIQUE (REQUEST_KEY)"),
            ("SJZQ_PRODUCT_SNAPSHOT", "UNIQUE (REQUEST_KEY)"),
            ("SJZQ_FIELD_PROVENANCE", "UNIQUE (SNAPSHOT_ID, FIELD_NAME)"),
            ("SJZQ_QUALITY_RESULT", "UNIQUE (RAW_ID)"),
            ("SJZQ_DATA_QUARANTINE", "UNIQUE (RAW_ID)"),
            ("SJZQ_SNAPSHOT_DIFF", "UNIQUE (SNAPSHOT_ID)"),
        ):
            self.assertIn(fragment, ddl_by_table[table])
        quarantine_ddl = ddl_by_table["SJZQ_DATA_QUARANTINE"]
        self.assertIn("QUALITY_RESULT_ID NUMBER(18) NOT NULL", quarantine_ddl)
        self.assertIn("REFERENCES SJZQ_QUALITY_RESULT(QUALITY_RESULT_ID)", quarantine_ddl)

    def test_legacy_links_are_additive(self) -> None:
        self.assertEqual(
            {
                ("SJZQ_UPLOAD_RECEIPT", "MASTER_PRODUCT_ID"),
                ("SJZQ_UPLOAD_RECEIPT", "SNAPSHOT_ID"),
                ("SJZQ_UPLOAD_RECEIPT", "QUARANTINE_ID"),
                ("SJZQ_PRODUCT", "MASTER_PRODUCT_ID"),
                ("SJZQ_PRODUCT", "SNAPSHOT_ID"),
            },
            {(table, column) for table, column, _ in P3_ADDITIVE_COLUMNS},
        )
        for _, column, _ in P3_ADDITIVE_COLUMNS:
            self.assertIn(column, INIT_SCHEMA)

    def test_version_record_and_rerun_contract_are_present(self) -> None:
        self.assertEqual(64, len(P3_MIGRATION_CHECKSUM))
        self.assertRegex(P3_MIGRATION_CHECKSUM, r"^[0-9a-f]{64}$")
        self.assertIn(P3_MIGRATION_ID, MIGRATE)
        self.assertIn("def _ensure_phase3_data_quality_schema", MIGRATE)
        self.assertIn("migration checksum mismatch", MIGRATE)
        self.assertIn("STATUS='applied'", MIGRATE)
        phase3 = MIGRATE[MIGRATE.index("def _ensure_phase3_data_quality_schema"):]
        self.assertNotIn("DROP TABLE", phase3)
        self.assertNotIn("DELETE FROM", phase3)

    def test_oracle_identifiers_stay_within_portable_limit(self) -> None:
        declarations = "\n".join(ddl for _, ddl in P3_TABLES)
        declarations += "\n".join(name for name, _ in P3_INDEXES)
        declarations += "\n".join(P3_SEQUENCES)
        identifiers = re.findall(r"(?:CONSTRAINT|INDEX)\s+([A-Z0-9_]+)", declarations)
        self.assertFalse([name for name in identifiers if len(name) > 30])
        self.assertFalse([name for name in P3_SEQUENCES if len(name) > 30])

    def test_applied_migration_rerun_does_not_recreate_objects(self) -> None:
        cursor = _MigrationCursor([(P3_MIGRATION_CHECKSUM, "applied")])
        conn = _MigrationConnection()
        with patch.object(migrate, "_ensure_table") as ensure_table, \
             patch.object(migrate, "_ensure_column") as ensure_column, \
             patch.object(migrate, "_ensure_sequence") as ensure_sequence, \
             patch.object(migrate, "_ensure_index") as ensure_index:
            migrate._ensure_phase3_data_quality_schema(conn, cursor)

        ensure_table.assert_called_once_with(cursor, *P3_TABLES[0])
        ensure_column.assert_not_called()
        ensure_sequence.assert_not_called()
        ensure_index.assert_not_called()
        self.assertEqual(0, conn.commits)

    def test_pending_migration_creates_each_guarded_object_then_marks_applied(self) -> None:
        cursor = _MigrationCursor([None])
        conn = _MigrationConnection()
        with patch.object(migrate, "_ensure_table") as ensure_table, \
             patch.object(migrate, "_ensure_column") as ensure_column, \
             patch.object(migrate, "_ensure_sequence") as ensure_sequence, \
             patch.object(migrate, "_ensure_index") as ensure_index:
            migrate._ensure_phase3_data_quality_schema(conn, cursor)

        self.assertEqual([P3_TABLES[0], *P3_TABLES[1:]], [call.args[1:] for call in ensure_table.call_args_list])
        self.assertEqual(len(P3_ADDITIVE_COLUMNS), ensure_column.call_count)
        self.assertEqual(len(P3_SEQUENCES), ensure_sequence.call_count)
        self.assertEqual(len(P3_INDEXES), ensure_index.call_count)
        self.assertEqual(2, conn.commits)
        self.assertTrue(any("STATUS='applied'" in sql for sql, _ in cursor.executed))


class _MigrationCursor:
    def __init__(self, rows: list[tuple[str, str] | None]) -> None:
        self._rows = list(rows)
        self.executed: list[tuple[str, dict | None]] = []

    def execute(self, sql: str, params: dict | None = None) -> None:
        self.executed.append((" ".join(sql.split()), params))

    def fetchone(self):
        return self._rows.pop(0)


class _MigrationConnection:
    def __init__(self) -> None:
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1


if __name__ == "__main__":
    unittest.main()
