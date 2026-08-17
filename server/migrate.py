"""Lightweight schema patches applied on server startup."""
from __future__ import annotations

from server.schema_migrations import (
    P3_ADDITIVE_COLUMNS,
    P3_INDEXES,
    P3_MIGRATION_CHECKSUM,
    P3_MIGRATION_DESCRIPTION,
    P3_MIGRATION_ID,
    P3_SEQUENCES,
    P3_TABLES,
    P4_INDEXES,
    P4_MIGRATION_CHECKSUM,
    P4_MIGRATION_DESCRIPTION,
    P4_MIGRATION_ID,
    P5_INDEXES,
    P5_MIGRATION_CHECKSUM,
    P5_MIGRATION_DESCRIPTION,
    P5_MIGRATION_ID,
    P5_SEQUENCES,
    P5_TABLES,
    P5_TENANT_COLUMNS,
    P5_FENCE_MIGRATION_CHECKSUM,
    P5_FENCE_MIGRATION_DESCRIPTION,
    P5_FENCE_MIGRATION_ID,
    P5_COMPAT_MIGRATION_CHECKSUM,
    P5_COMPAT_MIGRATION_DESCRIPTION,
    P5_COMPAT_MIGRATION_ID,
    P55_DEVICE_COLUMNS,
    P55_INDEXES,
    P55_MIGRATION_CHECKSUM,
    P55_MIGRATION_DESCRIPTION,
    P55_MIGRATION_ID,
    P55_SEQUENCES,
    P55_TABLES,
)


def ensure_schema_patches() -> None:
    # Delay configuration/pool loading so the declarative migration contract is
    # inspectable by offline tests without requiring deployment credentials.
    from server.db import get_conn

    with get_conn() as conn:
        cur = conn.cursor()
        _ensure_column(
            cur,
            table="SJZQ_DEVICE",
            column="KEYWORD_RUN_COUNT",
            ddl="ALTER TABLE SJZQ_DEVICE ADD (KEYWORD_RUN_COUNT NUMBER(18) DEFAULT 0 NOT NULL)",
        )
        _ensure_requirement_schema(cur)
        _ensure_progress_receipt(cur)
        _ensure_upload_receipt(cur)
        _ensure_product_quality_columns(cur)
        _ensure_remote_image_path_nullable(cur)
        _ensure_phase2_job_schema(cur)
        _ensure_phase3_data_quality_schema(conn, cur)
        _ensure_phase4_management_indexes(conn, cur)
        _ensure_phase5_enterprise_tenancy(conn, cur)
        _ensure_phase5_tenant_not_null(conn, cur)
        _ensure_phase5_legacy_defaults(conn, cur)
        _ensure_phase55_enterprise_hardening(conn, cur)
        _ensure_goods_library(cur)


def _ensure_phase55_enterprise_hardening(conn, cur) -> None:
    cur.execute("SELECT CHECKSUM,STATUS FROM SJZQ_SCHEMA_MIGRATION WHERE VERSION_ID=:id",
                {"id": P55_MIGRATION_ID})
    row = cur.fetchone()
    if row is not None and str(row[0]) != P55_MIGRATION_CHECKSUM:
        raise RuntimeError(f"migration checksum mismatch: {P55_MIGRATION_ID}")
    if row is not None and str(row[1]).lower() == "applied":
        return
    if row is None:
        cur.execute("""INSERT INTO SJZQ_SCHEMA_MIGRATION
            (VERSION_ID,CHECKSUM,DESCRIPTION,STATUS,STARTED_AT)
            VALUES (:id,:checksum,:description,'running',SYSTIMESTAMP)""",
            {"id": P55_MIGRATION_ID, "checksum": P55_MIGRATION_CHECKSUM,
             "description": P55_MIGRATION_DESCRIPTION})
    else:
        cur.execute("""UPDATE SJZQ_SCHEMA_MIGRATION SET STATUS='running',STARTED_AT=SYSTIMESTAMP,
            APPLIED_AT=NULL,ERROR_MESSAGE=NULL WHERE VERSION_ID=:id""", {"id": P55_MIGRATION_ID})
    conn.commit()
    try:
        for table, ddl in P55_TABLES:
            _ensure_table(cur, table, ddl)
        for table, column, ddl in P55_DEVICE_COLUMNS:
            _ensure_column(cur, table, column, ddl)
        for sequence in P55_SEQUENCES:
            _ensure_sequence(cur, sequence)
        for name, ddl in P55_INDEXES:
            _ensure_index(cur, name, ddl)
        # Phase 5 adopts the legacy/default rows with deterministic ID 1.  On
        # a fresh installation those direct inserts can be ahead of sequences
        # that have never produced a value, so advance both generators before
        # the first real enterprise/workspace is created.
        _ensure_sequence_above_table(cur, "SJZQ_SEQ_ENTERPRISE", "SJZQ_ENTERPRISE", "ENTERPRISE_ID")
        _ensure_sequence_above_table(cur, "SJZQ_SEQ_WORKSPACE", "SJZQ_WORKSPACE", "WORKSPACE_ID")
        # Phase 5 added tenant columns after the legacy global account unique
        # key. Replace it only in the hardening migration so released P5
        # checksums stay immutable and equal account names can exist per tenant.
        cur.execute("""SELECT COUNT(*) FROM USER_CONSTRAINTS
                         WHERE TABLE_NAME='SJZQ_PLATFORM_ACCOUNT'
                           AND CONSTRAINT_NAME='UK_SJZQ_PLATFORM_ACCOUNT'""")
        if int(cur.fetchone()[0] or 0):
            cur.execute("ALTER TABLE SJZQ_PLATFORM_ACCOUNT DROP CONSTRAINT UK_SJZQ_PLATFORM_ACCOUNT")
        _ensure_constraint(cur, "SJZQ_PLATFORM_ACCOUNT", "UK_SJZQ_ACCOUNT_TENANT",
                           "ALTER TABLE SJZQ_PLATFORM_ACCOUNT ADD CONSTRAINT UK_SJZQ_ACCOUNT_TENANT "
                           "UNIQUE (ENTERPRISE_ID,WORKSPACE_ID,PLATFORM_CODE,ACCOUNT_NAME)")
        # Establish the ledger from persisted facts before write-time gates are
        # enabled. Active tasks get resource rows so their eventual terminal
        # transition can release exactly once.
        cur.execute("""INSERT INTO SJZQ_QUOTA_RESERVATION
            (RESERVATION_ID,ENTERPRISE_ID,WORKSPACE_ID,METRIC_CODE,PERIOD_KEY,AMOUNT,
             RESOURCE_TYPE,RESOURCE_KEY,STATUS,COMMITTED_AT)
            SELECT SJZQ_SEQ_QUOTA_RESERVATION.NEXTVAL,t.ENTERPRISE_ID,t.WORKSPACE_ID,
                   'active_task','lifetime',1,'task',TO_CHAR(t.TASK_ID),'committed',SYSTIMESTAMP
              FROM SJZQ_TASK t WHERE t.STATUS IN ('pending','running')
               AND NOT EXISTS (SELECT 1 FROM SJZQ_QUOTA_RESERVATION r
                  WHERE r.ENTERPRISE_ID=t.ENTERPRISE_ID AND r.METRIC_CODE='active_task'
                    AND r.PERIOD_KEY='lifetime' AND r.RESOURCE_TYPE='task'
                    AND r.RESOURCE_KEY=TO_CHAR(t.TASK_ID))""")
        cur.execute("""MERGE INTO SJZQ_QUOTA_USAGE u USING (
            SELECT ENTERPRISE_ID,'active_task' METRIC_CODE,'lifetime' PERIOD_KEY,COUNT(*) USED_VALUE
              FROM SJZQ_TASK WHERE STATUS IN ('pending','running') GROUP BY ENTERPRISE_ID
            ) x ON (u.ENTERPRISE_ID=x.ENTERPRISE_ID AND u.METRIC_CODE=x.METRIC_CODE AND u.PERIOD_KEY=x.PERIOD_KEY)
            WHEN MATCHED THEN UPDATE SET u.USED_VALUE=x.USED_VALUE,u.RESERVED_VALUE=0,u.UPDATE_TIME=SYSTIMESTAMP
            WHEN NOT MATCHED THEN INSERT (ENTERPRISE_ID,METRIC_CODE,PERIOD_KEY,USED_VALUE,RESERVED_VALUE)
              VALUES (x.ENTERPRISE_ID,x.METRIC_CODE,x.PERIOD_KEY,x.USED_VALUE,0)""")
        cur.execute("""INSERT INTO SJZQ_QUOTA_LEDGER
            (LEDGER_ID,ENTERPRISE_ID,WORKSPACE_ID,METRIC_CODE,PERIOD_KEY,EVENT_TYPE,
             EVENT_KEY,DELTA_USED,DELTA_RESERVED,RESOURCE_TYPE,RESOURCE_KEY)
            SELECT SJZQ_SEQ_QUOTA_LEDGER.NEXTVAL,u.ENTERPRISE_ID,
                   NVL((SELECT MIN(w.WORKSPACE_ID) FROM SJZQ_WORKSPACE w WHERE w.ENTERPRISE_ID=u.ENTERPRISE_ID),1),
                   u.METRIC_CODE,u.PERIOD_KEY,'backfill',
                   'p55-backfill:'||TO_CHAR(u.ENTERPRISE_ID)||':'||u.METRIC_CODE||':'||u.PERIOD_KEY,
                   u.USED_VALUE,0,'migration','P5.5'
              FROM SJZQ_QUOTA_USAGE u
             WHERE NOT EXISTS (SELECT 1 FROM SJZQ_QUOTA_LEDGER l
                    WHERE l.EVENT_KEY='p55-backfill:'||TO_CHAR(u.ENTERPRISE_ID)||':'||u.METRIC_CODE||':'||u.PERIOD_KEY)""")
        cur.execute("""MERGE INTO SJZQ_QUOTA_USAGE u USING (
            SELECT ENTERPRISE_ID,'daily_snapshot' METRIC_CODE,TO_CHAR(SYSDATE,'YYYY-MM-DD') PERIOD_KEY,COUNT(*) USED_VALUE
              FROM SJZQ_PRODUCT_SNAPSHOT WHERE COLLECTED_AT>=TRUNC(SYSDATE) GROUP BY ENTERPRISE_ID
            ) x ON (u.ENTERPRISE_ID=x.ENTERPRISE_ID AND u.METRIC_CODE=x.METRIC_CODE AND u.PERIOD_KEY=x.PERIOD_KEY)
            WHEN MATCHED THEN UPDATE SET u.USED_VALUE=x.USED_VALUE,u.RESERVED_VALUE=0,u.UPDATE_TIME=SYSTIMESTAMP
            WHEN NOT MATCHED THEN INSERT (ENTERPRISE_ID,METRIC_CODE,PERIOD_KEY,USED_VALUE,RESERVED_VALUE)
              VALUES (x.ENTERPRISE_ID,x.METRIC_CODE,x.PERIOD_KEY,x.USED_VALUE,0)""")
        cur.execute("""MERGE INTO SJZQ_QUOTA_USAGE u USING (
            SELECT ENTERPRISE_ID,'storage_bytes' METRIC_CODE,'lifetime' PERIOD_KEY,SUM(BYTES_USED) USED_VALUE
              FROM (SELECT ENTERPRISE_ID,NVL(SUM(DBMS_LOB.GETLENGTH(RAW_JSON)),0) BYTES_USED FROM SJZQ_RAW_COLLECTION GROUP BY ENTERPRISE_ID
                    UNION ALL SELECT ENTERPRISE_ID,NVL(SUM(FILE_SIZE),0) FROM SJZQ_PRODUCT_IMAGE GROUP BY ENTERPRISE_ID)
             GROUP BY ENTERPRISE_ID
            ) x ON (u.ENTERPRISE_ID=x.ENTERPRISE_ID AND u.METRIC_CODE=x.METRIC_CODE AND u.PERIOD_KEY=x.PERIOD_KEY)
            WHEN MATCHED THEN UPDATE SET u.USED_VALUE=x.USED_VALUE,u.RESERVED_VALUE=0,u.UPDATE_TIME=SYSTIMESTAMP
            WHEN NOT MATCHED THEN INSERT (ENTERPRISE_ID,METRIC_CODE,PERIOD_KEY,USED_VALUE,RESERVED_VALUE)
              VALUES (x.ENTERPRISE_ID,x.METRIC_CODE,x.PERIOD_KEY,x.USED_VALUE,0)""")
        cur.execute("""INSERT INTO SJZQ_QUOTA_LEDGER
            (LEDGER_ID,ENTERPRISE_ID,WORKSPACE_ID,METRIC_CODE,PERIOD_KEY,EVENT_TYPE,
             EVENT_KEY,DELTA_USED,DELTA_RESERVED,RESOURCE_TYPE,RESOURCE_KEY)
            SELECT SJZQ_SEQ_QUOTA_LEDGER.NEXTVAL,u.ENTERPRISE_ID,
                   NVL((SELECT MIN(w.WORKSPACE_ID) FROM SJZQ_WORKSPACE w WHERE w.ENTERPRISE_ID=u.ENTERPRISE_ID),1),
                   u.METRIC_CODE,u.PERIOD_KEY,'backfill',
                   'p55-backfill:'||TO_CHAR(u.ENTERPRISE_ID)||':'||u.METRIC_CODE||':'||u.PERIOD_KEY,
                   u.USED_VALUE,0,'migration','P5.5'
              FROM SJZQ_QUOTA_USAGE u
             WHERE NOT EXISTS (SELECT 1 FROM SJZQ_QUOTA_LEDGER l
                    WHERE l.EVENT_KEY='p55-backfill:'||TO_CHAR(u.ENTERPRISE_ID)||':'||u.METRIC_CODE||':'||u.PERIOD_KEY)""")
        cur.execute("""UPDATE SJZQ_SCHEMA_MIGRATION SET STATUS='applied',APPLIED_AT=SYSTIMESTAMP,
            ERROR_MESSAGE=NULL WHERE VERSION_ID=:id""", {"id": P55_MIGRATION_ID})
        conn.commit()
        print(f"[migrate] applied {P55_MIGRATION_ID}")
    except Exception as exc:
        cur.execute("UPDATE SJZQ_SCHEMA_MIGRATION SET STATUS='failed',ERROR_MESSAGE=:error WHERE VERSION_ID=:id",
                    {"id": P55_MIGRATION_ID, "error": str(exc)[:2000]})
        conn.commit()
        raise


def _ensure_phase5_legacy_defaults(conn, cur) -> None:
    cur.execute("SELECT CHECKSUM,STATUS FROM SJZQ_SCHEMA_MIGRATION WHERE VERSION_ID=:id", {"id":P5_COMPAT_MIGRATION_ID})
    row=cur.fetchone()
    if row is not None and str(row[0]) != P5_COMPAT_MIGRATION_CHECKSUM:
        raise RuntimeError(f"migration checksum mismatch: {P5_COMPAT_MIGRATION_ID}")
    if row is not None and str(row[1]).lower()=="applied": return
    if row is None:
        cur.execute("""INSERT INTO SJZQ_SCHEMA_MIGRATION
            (VERSION_ID,CHECKSUM,DESCRIPTION,STATUS,STARTED_AT) VALUES (:id,:checksum,:description,'running',SYSTIMESTAMP)""",
            {"id":P5_COMPAT_MIGRATION_ID,"checksum":P5_COMPAT_MIGRATION_CHECKSUM,"description":P5_COMPAT_MIGRATION_DESCRIPTION})
    conn.commit()
    required={"SJZQ_DEVICE","SJZQ_TASK","SJZQ_COLLECTION_JOB","SJZQ_COLLECTION_ATTEMPT","SJZQ_COLLECTION_LEASE",
              "SJZQ_COLLECTION_CHECKPOINT","SJZQ_JOB_EVENT","SJZQ_TASK_ITEM","SJZQ_TASK_LOG","SJZQ_UPLOAD_RECEIPT",
              "SJZQ_PRODUCT","SJZQ_PRODUCT_IMAGE","SJZQ_RAW_COLLECTION","SJZQ_PRODUCT_SNAPSHOT","SJZQ_QUALITY_RESULT",
              "SJZQ_DATA_QUARANTINE","SJZQ_SNAPSHOT_DIFF"}
    try:
        for table,definitions in P5_TENANT_COLUMNS:
            if table not in required: continue
            columns={x.strip().split()[0] for x in definitions.split(",")}
            for column in ("ENTERPRISE_ID","WORKSPACE_ID"):
                if column in columns: cur.execute(f"ALTER TABLE {table} MODIFY ({column} DEFAULT 1)")
        cur.execute("UPDATE SJZQ_SCHEMA_MIGRATION SET STATUS='applied',APPLIED_AT=SYSTIMESTAMP WHERE VERSION_ID=:id",
                    {"id":P5_COMPAT_MIGRATION_ID}); conn.commit(); print(f"[migrate] applied {P5_COMPAT_MIGRATION_ID}")
    except Exception as exc:
        cur.execute("UPDATE SJZQ_SCHEMA_MIGRATION SET STATUS='failed',ERROR_MESSAGE=:error WHERE VERSION_ID=:id",
                    {"id":P5_COMPAT_MIGRATION_ID,"error":str(exc)[:2000]}); conn.commit(); raise


def _ensure_phase5_tenant_not_null(conn, cur) -> None:
    cur.execute("SELECT CHECKSUM,STATUS FROM SJZQ_SCHEMA_MIGRATION WHERE VERSION_ID=:id", {"id":P5_FENCE_MIGRATION_ID})
    row=cur.fetchone()
    if row is not None and str(row[0]) != P5_FENCE_MIGRATION_CHECKSUM:
        raise RuntimeError(f"migration checksum mismatch: {P5_FENCE_MIGRATION_ID}")
    if row is not None and str(row[1]).lower() == "applied": return
    if row is None:
        cur.execute("""INSERT INTO SJZQ_SCHEMA_MIGRATION
            (VERSION_ID,CHECKSUM,DESCRIPTION,STATUS,STARTED_AT) VALUES (:id,:checksum,:description,'running',SYSTIMESTAMP)""",
            {"id":P5_FENCE_MIGRATION_ID,"checksum":P5_FENCE_MIGRATION_CHECKSUM,"description":P5_FENCE_MIGRATION_DESCRIPTION})
    conn.commit()
    try:
        required_tables = {
            "SJZQ_DEVICE","SJZQ_TASK","SJZQ_COLLECTION_JOB","SJZQ_COLLECTION_ATTEMPT",
            "SJZQ_COLLECTION_LEASE","SJZQ_COLLECTION_CHECKPOINT","SJZQ_JOB_EVENT",
            "SJZQ_TASK_ITEM","SJZQ_TASK_LOG","SJZQ_UPLOAD_RECEIPT","SJZQ_PRODUCT",
            "SJZQ_PRODUCT_IMAGE","SJZQ_RAW_COLLECTION","SJZQ_PRODUCT_SNAPSHOT",
            "SJZQ_QUALITY_RESULT","SJZQ_DATA_QUARANTINE","SJZQ_SNAPSHOT_DIFF",
        }
        for table, definitions in P5_TENANT_COLUMNS:
            if table not in required_tables:
                continue
            columns={x.strip().split()[0] for x in definitions.split(",")}
            for column in ("ENTERPRISE_ID","WORKSPACE_ID"):
                if column in columns:
                    cur.execute(f"UPDATE {table} SET {column}=1 WHERE {column} IS NULL")
                    cur.execute(f"ALTER TABLE {table} MODIFY ({column} NOT NULL)")
        cur.execute("UPDATE SJZQ_SCHEMA_MIGRATION SET STATUS='applied',APPLIED_AT=SYSTIMESTAMP,ERROR_MESSAGE=NULL WHERE VERSION_ID=:id",
                    {"id":P5_FENCE_MIGRATION_ID})
        conn.commit(); print(f"[migrate] applied {P5_FENCE_MIGRATION_ID}")
    except Exception as exc:
        cur.execute("UPDATE SJZQ_SCHEMA_MIGRATION SET STATUS='failed',ERROR_MESSAGE=:error WHERE VERSION_ID=:id",
                    {"id":P5_FENCE_MIGRATION_ID,"error":str(exc)[:2000]})
        conn.commit(); raise


def _ensure_phase5_enterprise_tenancy(conn, cur) -> None:
    """Restartable additive tenant migration with a deterministic legacy tenant."""
    migration_table, migration_ddl = P3_TABLES[0]
    _ensure_table(cur, migration_table, migration_ddl)
    cur.execute("SELECT CHECKSUM,STATUS FROM SJZQ_SCHEMA_MIGRATION WHERE VERSION_ID=:id", {"id": P5_MIGRATION_ID})
    row = cur.fetchone()
    if row is not None and str(row[0]) != P5_MIGRATION_CHECKSUM:
        raise RuntimeError(f"migration checksum mismatch: {P5_MIGRATION_ID}")
    if row is not None and str(row[1]).lower() == "applied":
        return
    if row is None:
        cur.execute("""INSERT INTO SJZQ_SCHEMA_MIGRATION
            (VERSION_ID,CHECKSUM,DESCRIPTION,STATUS,STARTED_AT)
            VALUES (:id,:checksum,:description,'running',SYSTIMESTAMP)""",
            {"id": P5_MIGRATION_ID, "checksum": P5_MIGRATION_CHECKSUM, "description": P5_MIGRATION_DESCRIPTION})
    else:
        cur.execute("""UPDATE SJZQ_SCHEMA_MIGRATION SET STATUS='running',STARTED_AT=SYSTIMESTAMP,
            APPLIED_AT=NULL,ERROR_MESSAGE=NULL WHERE VERSION_ID=:id""", {"id": P5_MIGRATION_ID})
    conn.commit()
    try:
        for table, ddl in P5_TABLES:
            _ensure_table(cur, table, ddl)
        for sequence in P5_SEQUENCES:
            _ensure_sequence(cur, sequence)
        # Oracle only supports a single ADD operation here reliably across the
        # supported versions, so split the declarative column groups.
        for table, definitions in P5_TENANT_COLUMNS:
            for definition in [x.strip() for x in definitions.split(",")]:
                column = definition.split()[0]
                _ensure_column(cur, table, column, f"ALTER TABLE {table} ADD ({definition})")

        # Existing single-space installations are adopted into an explicit
        # deterministic tenant.  New writes never rely on this fallback.
        cur.execute("SELECT COUNT(*) FROM SJZQ_ENTERPRISE WHERE ENTERPRISE_ID=1")
        if int(cur.fetchone()[0]) == 0:
            cur.execute("""INSERT INTO SJZQ_ENTERPRISE
                (ENTERPRISE_ID,ENTERPRISE_CODE,ENTERPRISE_NAME,STATUS)
                VALUES (1,'legacy','Legacy Enterprise','active')""")
        cur.execute("SELECT COUNT(*) FROM SJZQ_WORKSPACE WHERE WORKSPACE_ID=1")
        if int(cur.fetchone()[0]) == 0:
            cur.execute("""INSERT INTO SJZQ_WORKSPACE
                (WORKSPACE_ID,ENTERPRISE_ID,WORKSPACE_CODE,WORKSPACE_NAME,STATUS)
                VALUES (1,1,'default','Default Workspace','active')""")
        cur.execute("SELECT COUNT(*) FROM SJZQ_ENTERPRISE_QUOTA WHERE ENTERPRISE_ID=1")
        if int(cur.fetchone()[0]) == 0:
            cur.execute("INSERT INTO SJZQ_ENTERPRISE_QUOTA (ENTERPRISE_ID) VALUES (1)")
        for table, definitions in P5_TENANT_COLUMNS:
            columns = {x.strip().split()[0] for x in definitions.split(",")}
            if "ENTERPRISE_ID" in columns:
                cur.execute(f"UPDATE {table} SET ENTERPRISE_ID=1 WHERE ENTERPRISE_ID IS NULL")
            if "WORKSPACE_ID" in columns:
                cur.execute(f"UPDATE {table} SET WORKSPACE_ID=1 WHERE WORKSPACE_ID IS NULL")
        # Every existing user becomes an active member of the adopted tenant.
        cur.execute("""INSERT INTO SJZQ_ENTERPRISE_MEMBERSHIP
            (MEMBERSHIP_ID,ENTERPRISE_ID,USER_ID,ROLE_ID,STATUS)
            SELECT SJZQ_SEQ_ENT_MEMBERSHIP.NEXTVAL,1,u.USER_ID,u.ROLE_ID,'active'
              FROM SJZQ_USER u
             WHERE NOT EXISTS (SELECT 1 FROM SJZQ_ENTERPRISE_MEMBERSHIP m
                                WHERE m.ENTERPRISE_ID=1 AND m.USER_ID=u.USER_ID)""")
        for name, ddl in P5_INDEXES:
            _ensure_index(cur, name, ddl)
        cur.execute("""UPDATE SJZQ_SCHEMA_MIGRATION SET STATUS='applied',APPLIED_AT=SYSTIMESTAMP,
            ERROR_MESSAGE=NULL WHERE VERSION_ID=:id""", {"id": P5_MIGRATION_ID})
        conn.commit()
        print(f"[migrate] applied {P5_MIGRATION_ID}")
    except Exception as exc:
        cur.execute("UPDATE SJZQ_SCHEMA_MIGRATION SET STATUS='failed',ERROR_MESSAGE=:error WHERE VERSION_ID=:id",
                    {"id": P5_MIGRATION_ID, "error": str(exc)[:2000]})
        conn.commit()
        raise


def _ensure_phase4_management_indexes(conn, cur) -> None:
    cur.execute(
        "SELECT CHECKSUM,STATUS FROM SJZQ_SCHEMA_MIGRATION WHERE VERSION_ID=:version_id",
        {"version_id": P4_MIGRATION_ID},
    )
    row = cur.fetchone()
    if row is not None and str(row[0]) != P4_MIGRATION_CHECKSUM:
        raise RuntimeError(f"migration checksum mismatch: {P4_MIGRATION_ID}")
    if row is not None and str(row[1]).lower() == "applied":
        return
    if row is None:
        cur.execute(
            """INSERT INTO SJZQ_SCHEMA_MIGRATION
               (VERSION_ID,CHECKSUM,DESCRIPTION,STATUS,STARTED_AT)
               VALUES (:version_id,:checksum,:description,'running',SYSTIMESTAMP)""",
            {"version_id": P4_MIGRATION_ID, "checksum": P4_MIGRATION_CHECKSUM,
             "description": P4_MIGRATION_DESCRIPTION},
        )
    else:
        cur.execute(
            """UPDATE SJZQ_SCHEMA_MIGRATION SET STATUS='running',STARTED_AT=SYSTIMESTAMP,
                      APPLIED_AT=NULL,ERROR_MESSAGE=NULL WHERE VERSION_ID=:version_id""",
            {"version_id": P4_MIGRATION_ID},
        )
    conn.commit()
    try:
        for name, ddl in P4_INDEXES:
            _ensure_index(cur, name, ddl)
        cur.execute(
            """UPDATE SJZQ_SCHEMA_MIGRATION SET STATUS='applied',APPLIED_AT=SYSTIMESTAMP,
                      ERROR_MESSAGE=NULL WHERE VERSION_ID=:version_id""",
            {"version_id": P4_MIGRATION_ID},
        )
        conn.commit()
        print(f"[migrate] applied {P4_MIGRATION_ID}")
    except Exception as exc:
        cur.execute(
            "UPDATE SJZQ_SCHEMA_MIGRATION SET STATUS='failed',ERROR_MESSAGE=:error WHERE VERSION_ID=:version_id",
            {"version_id": P4_MIGRATION_ID, "error": str(exc)[:2000]},
        )
        conn.commit()
        raise


def _ensure_phase3_data_quality_schema(conn, cur) -> None:
    """Apply ``P3_001_DATA_QUALITY``, the restartable Phase 3 migration.

    It installs SJZQ_SCHEMA_MIGRATION, SJZQ_PRODUCT_MASTER,
    SJZQ_RAW_COLLECTION, SJZQ_PRODUCT_SNAPSHOT, SJZQ_FIELD_PROVENANCE,
    SJZQ_QUALITY_RESULT, SJZQ_DATA_QUARANTINE, and SJZQ_SNAPSHOT_DIFF.

    Oracle commits DDL implicitly.  Each object is therefore guarded by its
    data-dictionary existence check rather than relying on a transaction to
    roll back a partially completed migration.  A failed run is marked failed
    and a subsequent startup re-enters the same migration safely.
    """
    migration_table, migration_ddl = P3_TABLES[0]
    _ensure_table(cur, migration_table, migration_ddl)
    cur.execute(
        "SELECT CHECKSUM, STATUS FROM SJZQ_SCHEMA_MIGRATION WHERE VERSION_ID=:version_id",
        {"version_id": P3_MIGRATION_ID},
    )
    row = cur.fetchone()
    if row is not None and str(row[0]) != P3_MIGRATION_CHECKSUM:
        raise RuntimeError(f"migration checksum mismatch: {P3_MIGRATION_ID}")
    if row is not None and str(row[1]).lower() == "applied":
        return

    if row is None:
        cur.execute(
            """
            INSERT INTO SJZQ_SCHEMA_MIGRATION
            (VERSION_ID, CHECKSUM, DESCRIPTION, STATUS, STARTED_AT, APPLIED_AT, ERROR_MESSAGE)
            VALUES (:version_id, :checksum, :description, 'running', SYSTIMESTAMP, NULL, NULL)
            """,
            {
                "version_id": P3_MIGRATION_ID,
                "checksum": P3_MIGRATION_CHECKSUM,
                "description": P3_MIGRATION_DESCRIPTION,
            },
        )
    else:
        cur.execute(
            """
            UPDATE SJZQ_SCHEMA_MIGRATION
               SET STATUS='running', STARTED_AT=SYSTIMESTAMP, APPLIED_AT=NULL, ERROR_MESSAGE=NULL
             WHERE VERSION_ID=:version_id
            """,
            {"version_id": P3_MIGRATION_ID},
        )
    # Persist the lifecycle row before a later Oracle DDL performs its own
    # implicit commit; that makes interrupted DDL visible as a resumable run.
    conn.commit()

    try:
        for table, ddl in P3_TABLES[1:]:
            _ensure_table(cur, table, ddl)
        for table, column, ddl in P3_ADDITIVE_COLUMNS:
            _ensure_column(cur, table, column, ddl)
        for sequence in P3_SEQUENCES:
            _ensure_sequence(cur, sequence)
        for name, ddl in P3_INDEXES:
            _ensure_index(cur, name, ddl)
        cur.execute(
            """
            UPDATE SJZQ_SCHEMA_MIGRATION
               SET STATUS='applied', APPLIED_AT=SYSTIMESTAMP, ERROR_MESSAGE=NULL
             WHERE VERSION_ID=:version_id
            """,
            {"version_id": P3_MIGRATION_ID},
        )
        conn.commit()
        print(f"[migrate] applied {P3_MIGRATION_ID}")
    except Exception as exc:
        cur.execute(
            """
            UPDATE SJZQ_SCHEMA_MIGRATION
               SET STATUS='failed', ERROR_MESSAGE=:error_message
             WHERE VERSION_ID=:version_id
            """,
            {"version_id": P3_MIGRATION_ID, "error_message": str(exc)[:2000]},
        )
        conn.commit()
        raise


def _ensure_progress_receipt(cur) -> None:
    if not _object_exists(cur, "SJZQ_PROGRESS_RECEIPT"):
        cur.execute(
            """
            CREATE TABLE SJZQ_PROGRESS_RECEIPT (
                PROGRESS_ID VARCHAR2(64) NOT NULL,
                TASK_ID NUMBER(18) NOT NULL,
                DEVICE_ID NUMBER(18) NOT NULL,
                CREATE_TIME TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
                CONSTRAINT PK_SJZQ_PROGRESS_RECEIPT PRIMARY KEY (PROGRESS_ID)
            )
            """
        )
        print("[migrate] created SJZQ_PROGRESS_RECEIPT")


def _ensure_upload_receipt(cur) -> None:
    if not _object_exists(cur, "SJZQ_UPLOAD_RECEIPT"):
        cur.execute(
            """
            CREATE TABLE SJZQ_UPLOAD_RECEIPT (
                IDEMPOTENCY_KEY VARCHAR2(128) NOT NULL,
                TASK_ID NUMBER(18),
                DEVICE_ID NUMBER(18) NOT NULL,
                OP_TYPE VARCHAR2(16) NOT NULL,
                PAYLOAD_SHA256 VARCHAR2(64) NOT NULL,
                PRODUCT_ID NUMBER(18),
                RESULT_JSON CLOB,
                STATUS VARCHAR2(16) DEFAULT 'acked' NOT NULL,
                CREATE_TIME TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
                ACK_TIME TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
                CONSTRAINT PK_SJZQ_UPLOAD_RECEIPT PRIMARY KEY (IDEMPOTENCY_KEY)
            )
            """
        )
        cur.execute(
            "CREATE INDEX IDX_SJZQ_RECEIPT_TASK ON SJZQ_UPLOAD_RECEIPT(TASK_ID, OP_TYPE, STATUS)"
        )
        print("[migrate] created SJZQ_UPLOAD_RECEIPT")


def _ensure_product_quality_columns(cur) -> None:
    for column, ddl in [
        ("PARSE_STATUS", "ALTER TABLE SJZQ_PRODUCT ADD (PARSE_STATUS VARCHAR2(16))"),
        ("PAGE_STATUS", "ALTER TABLE SJZQ_PRODUCT ADD (PAGE_STATUS VARCHAR2(32))"),
        ("QUALITY_STATUS", "ALTER TABLE SJZQ_PRODUCT ADD (QUALITY_STATUS VARCHAR2(16))"),
        ("FIELD_SOURCES", "ALTER TABLE SJZQ_PRODUCT ADD (FIELD_SOURCES CLOB)"),
        ("PARSER_VERSION", "ALTER TABLE SJZQ_PRODUCT ADD (PARSER_VERSION VARCHAR2(64))"),
        (
            "QUALITY_RULES_VERSION",
            "ALTER TABLE SJZQ_PRODUCT ADD (QUALITY_RULES_VERSION VARCHAR2(64))",
        ),
    ]:
        _ensure_column(cur, "SJZQ_PRODUCT", column, ddl)


def _ensure_remote_image_path_nullable(cur) -> None:
    """Remote-only image rows have SOURCE_URL but no local REL_PATH.

    Oracle normalizes an empty string to NULL, so REL_PATH must be nullable for
    the product JSON upload path. Local multipart uploads still always provide
    a concrete relative path.
    """
    cur.execute(
        """
        SELECT NULLABLE FROM USER_TAB_COLUMNS
         WHERE TABLE_NAME='SJZQ_PRODUCT_IMAGE' AND COLUMN_NAME='REL_PATH'
        """
    )
    row = cur.fetchone()
    if row and str(row[0]).upper() == "N":
        cur.execute("ALTER TABLE SJZQ_PRODUCT_IMAGE MODIFY (REL_PATH NULL)")
        print("[migrate] made SJZQ_PRODUCT_IMAGE.REL_PATH nullable")


def _ensure_column(cur, table: str, column: str, ddl: str) -> None:
    cur.execute(
        """
        SELECT COUNT(*) FROM USER_TAB_COLUMNS
         WHERE TABLE_NAME = :t AND COLUMN_NAME = :c
        """,
        {"t": table.upper(), "c": column.upper()},
    )
    if int(cur.fetchone()[0] or 0) == 0:
        cur.execute(ddl)
        print(f"[migrate] added {table}.{column}")


def _object_exists(cur, name: str) -> bool:
    cur.execute(
        """
        SELECT COUNT(*) FROM USER_OBJECTS
         WHERE OBJECT_NAME = :name AND OBJECT_TYPE IN ('TABLE', 'VIEW')
        """,
        {"name": name.upper()},
    )
    return int(cur.fetchone()[0] or 0) > 0


def _sequence_exists(cur, name: str) -> bool:
    cur.execute("SELECT COUNT(*) FROM USER_SEQUENCES WHERE SEQUENCE_NAME=:name", {"name": name.upper()})
    return int(cur.fetchone()[0] or 0) > 0


def _ensure_sequence(cur, name: str) -> None:
    if not _sequence_exists(cur, name):
        cur.execute(f"CREATE SEQUENCE {name} START WITH 1 INCREMENT BY 1 NOCACHE")
        print(f"[migrate] created sequence {name}")


def _ensure_sequence_above_table(cur, sequence: str, table: str, id_column: str) -> None:
    """Ensure the next generated ID cannot collide with directly seeded rows."""
    cur.execute(f"SELECT NVL(MAX({id_column}),0) FROM {table}")
    maximum = int(cur.fetchone()[0] or 0)
    cur.execute(f"SELECT {sequence}.NEXTVAL FROM DUAL")
    current = int(cur.fetchone()[0])
    if current <= maximum:
        increment = maximum + 1 - current
        cur.execute(f"ALTER SEQUENCE {sequence} INCREMENT BY {increment}")
        cur.execute(f"SELECT {sequence}.NEXTVAL FROM DUAL")
        cur.fetchone()
        cur.execute(f"ALTER SEQUENCE {sequence} INCREMENT BY 1")


def _ensure_index(cur, name: str, ddl: str) -> None:
    cur.execute("SELECT COUNT(*) FROM USER_INDEXES WHERE INDEX_NAME=:name", {"name": name.upper()})
    if int(cur.fetchone()[0] or 0) == 0:
        cur.execute(ddl)
        print(f"[migrate] created index {name}")


def _ensure_constraint(cur, table: str, name: str, ddl: str) -> None:
    cur.execute(
        "SELECT COUNT(*) FROM USER_CONSTRAINTS WHERE TABLE_NAME=:table_name AND CONSTRAINT_NAME=:name",
        {"table_name": table.upper(), "name": name.upper()},
    )
    if int(cur.fetchone()[0] or 0) == 0:
        cur.execute(ddl)
        print(f"[migrate] created constraint {name}")


def _ensure_table(cur, table: str, ddl: str) -> None:
    if not _object_exists(cur, table):
        cur.execute(ddl)
        print(f"[migrate] created {table}")


def _ensure_phase2_job_schema(cur) -> None:
    """Install the additive authoritative Job/Attempt/Lease substrate.

    The schema deliberately stores a hash of the bearer lease token.  Request
    handlers hash the supplied token before comparison, so an Oracle dump and
    structured event history never become a source of reusable lease rights.
    """
    for table, column, ddl in [
        ("SJZQ_TASK", "PAUSE_STATE", "ALTER TABLE SJZQ_TASK ADD (PAUSE_STATE VARCHAR2(16) DEFAULT 'active' NOT NULL)"),
        ("SJZQ_TASK", "PAUSE_REQUESTED", "ALTER TABLE SJZQ_TASK ADD (PAUSE_REQUESTED NUMBER(1) DEFAULT 0 NOT NULL)"),
        ("SJZQ_TASK", "DEADLINE_AT", "ALTER TABLE SJZQ_TASK ADD (DEADLINE_AT TIMESTAMP)"),
        ("SJZQ_TASK", "PAUSED_AT", "ALTER TABLE SJZQ_TASK ADD (PAUSED_AT TIMESTAMP)"),
        ("SJZQ_DEVICE", "ACTIVE_JOB_ID", "ALTER TABLE SJZQ_DEVICE ADD (ACTIVE_JOB_ID NUMBER(18))"),
        ("SJZQ_DEVICE", "ACTIVE_ATTEMPT_ID", "ALTER TABLE SJZQ_DEVICE ADD (ACTIVE_ATTEMPT_ID NUMBER(18))"),
    ]:
        _ensure_column(cur, table, column, ddl)
    _ensure_constraint(
        cur, "SJZQ_TASK", "CK_SJZQ_TASK_PAUSE_STATE",
        "ALTER TABLE SJZQ_TASK ADD CONSTRAINT CK_SJZQ_TASK_PAUSE_STATE CHECK (PAUSE_STATE IN ('active', 'paused'))",
    )
    _ensure_constraint(
        cur, "SJZQ_TASK", "CK_SJZQ_TASK_PAUSE_REQUESTED",
        "ALTER TABLE SJZQ_TASK ADD CONSTRAINT CK_SJZQ_TASK_PAUSE_REQUESTED CHECK (PAUSE_REQUESTED IN (0, 1))",
    )

    _ensure_table(cur, "SJZQ_COLLECTION_JOB", """
        CREATE TABLE SJZQ_COLLECTION_JOB (
            JOB_ID NUMBER(18) NOT NULL, TASK_ID NUMBER(18) NOT NULL,
            TASK_ITEM_ID NUMBER(18), DEVICE_ID NUMBER(18),
            JOB_KEY VARCHAR2(256) NOT NULL, JOB_TYPE VARCHAR2(32) NOT NULL,
            TARGET_JSON CLOB, STATUS VARCHAR2(16) DEFAULT 'pending' NOT NULL,
            PRIORITY NUMBER(5) DEFAULT 5 NOT NULL, MAX_ATTEMPTS NUMBER(5) DEFAULT 5 NOT NULL,
            ATTEMPT_COUNT NUMBER(5) DEFAULT 0 NOT NULL,
            NEXT_RUN_AT TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
            ACTIVE_ATTEMPT_ID NUMBER(18), LEASE_TOKEN_HASH VARCHAR2(64),
            LEASED_AT TIMESTAMP, LEASE_EXPIRES_AT TIMESTAMP, LAST_HEARTBEAT_AT TIMESTAMP,
            CHECKPOINT_VERSION NUMBER(10) DEFAULT 0 NOT NULL, CHECKPOINT_JSON CLOB,
            RESULT_RECEIPT_KEY VARCHAR2(128), RESULT_PRODUCT_ID NUMBER(18),
            PAUSE_REQUESTED NUMBER(1) DEFAULT 0 NOT NULL,
            LAST_ERROR_CLASS VARCHAR2(48), LAST_ERROR_CODE VARCHAR2(128),
            LAST_ERROR_MESSAGE VARCHAR2(2000),
            CREATE_TIME TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
            UPDATE_TIME TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
            CONSTRAINT PK_SJZQ_COLLECTION_JOB PRIMARY KEY (JOB_ID),
            CONSTRAINT UK_SJZQ_COLLECTION_JOB_KEY UNIQUE (JOB_KEY),
            CONSTRAINT CK_SJZQ_JOB_STATUS CHECK (STATUS IN ('pending','leased','running','paused','retry_wait','success','failed','cancelled','dead','quarantined')),
            CONSTRAINT CK_SJZQ_JOB_ATTEMPTS CHECK (MAX_ATTEMPTS >= 1 AND ATTEMPT_COUNT >= 0),
            CONSTRAINT CK_SJZQ_JOB_PAUSE_REQUESTED CHECK (PAUSE_REQUESTED IN (0,1)),
            CONSTRAINT FK_SJZQ_JOB_TASK FOREIGN KEY (TASK_ID) REFERENCES SJZQ_TASK(TASK_ID),
            CONSTRAINT FK_SJZQ_JOB_ITEM FOREIGN KEY (TASK_ITEM_ID) REFERENCES SJZQ_TASK_ITEM(ITEM_ID),
            CONSTRAINT FK_SJZQ_JOB_DEVICE FOREIGN KEY (DEVICE_ID) REFERENCES SJZQ_DEVICE(DEVICE_ID)
        )
    """)
    _ensure_table(cur, "SJZQ_COLLECTION_ATTEMPT", """
        CREATE TABLE SJZQ_COLLECTION_ATTEMPT (
            ATTEMPT_ID NUMBER(18) NOT NULL, JOB_ID NUMBER(18) NOT NULL,
            ATTEMPT_NO NUMBER(5) NOT NULL, DEVICE_ID NUMBER(18), WORKER_ID VARCHAR2(128),
            LEASE_TOKEN_HASH VARCHAR2(64) NOT NULL, TRACE_ID VARCHAR2(128) NOT NULL,
            STATUS VARCHAR2(16) DEFAULT 'leased' NOT NULL,
            LEASED_AT TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL, STARTED_AT TIMESTAMP,
            HEARTBEAT_AT TIMESTAMP, LEASE_EXPIRES_AT TIMESTAMP NOT NULL, FINISHED_AT TIMESTAMP,
            ERROR_CLASS VARCHAR2(48), ERROR_CODE VARCHAR2(128), ERROR_MESSAGE VARCHAR2(2000),
            RETRYABLE NUMBER(1), RETRY_DELAY_SECONDS NUMBER(10),
            START_CHECKPOINT_VERSION NUMBER(10) DEFAULT 0 NOT NULL,
            FINAL_CHECKPOINT_VERSION NUMBER(10), CREATE_TIME TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
            CONSTRAINT PK_SJZQ_COLLECTION_ATTEMPT PRIMARY KEY (ATTEMPT_ID),
            CONSTRAINT UK_SJZQ_ATTEMPT_NO UNIQUE (JOB_ID, ATTEMPT_NO),
            CONSTRAINT UK_SJZQ_ATTEMPT_LEASE_TOKEN UNIQUE (LEASE_TOKEN_HASH),
            CONSTRAINT CK_SJZQ_ATTEMPT_STATUS CHECK (STATUS IN ('leased','running','success','failed','timeout','cancelled','reclaimed')),
            CONSTRAINT CK_SJZQ_ATTEMPT_RETRYABLE CHECK (RETRYABLE IN (0,1) OR RETRYABLE IS NULL),
            CONSTRAINT CK_SJZQ_ATTEMPT_NUMBERS CHECK (ATTEMPT_NO >= 1 AND START_CHECKPOINT_VERSION >= 0 AND (FINAL_CHECKPOINT_VERSION IS NULL OR FINAL_CHECKPOINT_VERSION >= 0)),
            CONSTRAINT FK_SJZQ_ATTEMPT_JOB FOREIGN KEY (JOB_ID) REFERENCES SJZQ_COLLECTION_JOB(JOB_ID),
            CONSTRAINT FK_SJZQ_ATTEMPT_DEVICE FOREIGN KEY (DEVICE_ID) REFERENCES SJZQ_DEVICE(DEVICE_ID)
        )
    """)
    _ensure_table(cur, "SJZQ_COLLECTION_LEASE", """
        CREATE TABLE SJZQ_COLLECTION_LEASE (
            LEASE_ID NUMBER(18) NOT NULL, JOB_ID NUMBER(18) NOT NULL, ATTEMPT_ID NUMBER(18) NOT NULL,
            WORKER_ID VARCHAR2(128), DEVICE_ID NUMBER(18), LEASE_TOKEN_HASH VARCHAR2(64) NOT NULL,
            STATUS VARCHAR2(16) DEFAULT 'active' NOT NULL, LEASED_AT TIMESTAMP NOT NULL,
            LEASE_EXPIRES_AT TIMESTAMP NOT NULL, HEARTBEAT_AT TIMESTAMP, RELEASED_AT TIMESTAMP,
            RECLAIMED_AT TIMESTAMP, RELEASE_REASON VARCHAR2(128),
            CREATE_TIME TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
            CONSTRAINT PK_SJZQ_COLLECTION_LEASE PRIMARY KEY (LEASE_ID),
            CONSTRAINT UK_SJZQ_LEASE_ATTEMPT UNIQUE (ATTEMPT_ID),
            CONSTRAINT UK_SJZQ_COLLECTION_LEASE_TOKEN UNIQUE (LEASE_TOKEN_HASH),
            CONSTRAINT CK_SJZQ_LEASE_STATUS CHECK (STATUS IN ('active','released','reclaimed','expired')),
            CONSTRAINT CK_SJZQ_COLLECTION_LEASE_DATES CHECK (LEASE_EXPIRES_AT >= LEASED_AT),
            CONSTRAINT FK_SJZQ_COLLECTION_LEASE_JOB FOREIGN KEY (JOB_ID) REFERENCES SJZQ_COLLECTION_JOB(JOB_ID),
            CONSTRAINT FK_SJZQ_LEASE_ATTEMPT FOREIGN KEY (ATTEMPT_ID) REFERENCES SJZQ_COLLECTION_ATTEMPT(ATTEMPT_ID),
            CONSTRAINT FK_SJZQ_LEASE_DEVICE FOREIGN KEY (DEVICE_ID) REFERENCES SJZQ_DEVICE(DEVICE_ID)
        )
    """)
    _ensure_table(cur, "SJZQ_COLLECTION_CHECKPOINT", """
        CREATE TABLE SJZQ_COLLECTION_CHECKPOINT (
            CHECKPOINT_ID NUMBER(18) NOT NULL, JOB_ID NUMBER(18) NOT NULL, ATTEMPT_ID NUMBER(18),
            VERSION NUMBER(10) NOT NULL, IDEMPOTENCY_KEY VARCHAR2(128) NOT NULL,
            PAYLOAD_SHA256 VARCHAR2(64) NOT NULL, PAYLOAD_JSON CLOB NOT NULL,
            CREATE_TIME TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
            CONSTRAINT PK_SJZQ_COLLECTION_CHECKPOINT PRIMARY KEY (CHECKPOINT_ID),
            CONSTRAINT UK_SJZQ_CKPT_JOB_VER UNIQUE (JOB_ID, VERSION),
            CONSTRAINT UK_SJZQ_CKPT_JOB_IDEM UNIQUE (JOB_ID, IDEMPOTENCY_KEY),
            CONSTRAINT CK_SJZQ_CKPT_VERSION CHECK (VERSION >= 1),
            CONSTRAINT FK_SJZQ_CHECKPOINT_JOB FOREIGN KEY (JOB_ID) REFERENCES SJZQ_COLLECTION_JOB(JOB_ID),
            CONSTRAINT FK_SJZQ_CHECKPOINT_ATTEMPT FOREIGN KEY (ATTEMPT_ID) REFERENCES SJZQ_COLLECTION_ATTEMPT(ATTEMPT_ID)
        )
    """)
    _ensure_table(cur, "SJZQ_COLLECTION_OUTBOX", """
        CREATE TABLE SJZQ_COLLECTION_OUTBOX (
            OUTBOX_ID NUMBER(18) NOT NULL, EVENT_KEY VARCHAR2(128) NOT NULL,
            EVENT_TYPE VARCHAR2(64) NOT NULL, AGGREGATE_TYPE VARCHAR2(32) NOT NULL,
            TASK_ID NUMBER(18), JOB_ID NUMBER(18), ATTEMPT_ID NUMBER(18), PAYLOAD_JSON CLOB NOT NULL,
            STATUS VARCHAR2(16) DEFAULT 'pending' NOT NULL, AVAILABLE_AT TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
            DELIVERY_ATTEMPTS NUMBER(10) DEFAULT 0 NOT NULL, LOCK_TOKEN VARCHAR2(128), LOCKED_AT TIMESTAMP,
            LOCK_EXPIRES_AT TIMESTAMP, LAST_ERROR_CODE VARCHAR2(128), LAST_ERROR_MESSAGE VARCHAR2(2000),
            PUBLISHED_AT TIMESTAMP, CREATE_TIME TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
            UPDATE_TIME TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
            CONSTRAINT PK_SJZQ_COLLECTION_OUTBOX PRIMARY KEY (OUTBOX_ID),
            CONSTRAINT UK_SJZQ_OUTBOX_EVENT UNIQUE (EVENT_KEY),
            CONSTRAINT CK_SJZQ_OUTBOX_STATUS CHECK (STATUS IN ('pending','leased','delivered','dead')),
            CONSTRAINT CK_SJZQ_OUTBOX_ATTEMPTS CHECK (DELIVERY_ATTEMPTS >= 0),
            CONSTRAINT FK_SJZQ_OUTBOX_TASK FOREIGN KEY (TASK_ID) REFERENCES SJZQ_TASK(TASK_ID),
            CONSTRAINT FK_SJZQ_OUTBOX_JOB FOREIGN KEY (JOB_ID) REFERENCES SJZQ_COLLECTION_JOB(JOB_ID),
            CONSTRAINT FK_SJZQ_OUTBOX_ATTEMPT FOREIGN KEY (ATTEMPT_ID) REFERENCES SJZQ_COLLECTION_ATTEMPT(ATTEMPT_ID)
        )
    """)
    _ensure_table(cur, "SJZQ_JOB_EVENT", """
        CREATE TABLE SJZQ_JOB_EVENT (
            EVENT_ID NUMBER(18) NOT NULL, EVENT_KEY VARCHAR2(128) NOT NULL,
            TASK_ID NUMBER(18), JOB_ID NUMBER(18), ATTEMPT_ID NUMBER(18), DEVICE_ID NUMBER(18),
            WORKER_ID VARCHAR2(128), LEASE_TOKEN_HASH VARCHAR2(64), TRACE_ID VARCHAR2(128),
            EVENT_TYPE VARCHAR2(64) NOT NULL, OLD_STATUS VARCHAR2(16), NEW_STATUS VARCHAR2(16),
            ERROR_CLASS VARCHAR2(48), ERROR_CODE VARCHAR2(128), DETAIL_JSON CLOB,
            CREATE_TIME TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
            CONSTRAINT PK_SJZQ_JOB_EVENT PRIMARY KEY (EVENT_ID),
            CONSTRAINT UK_SJZQ_JOB_EVENT_KEY UNIQUE (EVENT_KEY),
            CONSTRAINT FK_SJZQ_JOB_EVENT_TASK FOREIGN KEY (TASK_ID) REFERENCES SJZQ_TASK(TASK_ID),
            CONSTRAINT FK_SJZQ_JOB_EVENT_JOB FOREIGN KEY (JOB_ID) REFERENCES SJZQ_COLLECTION_JOB(JOB_ID),
            CONSTRAINT FK_SJZQ_JOB_EVENT_ATTEMPT FOREIGN KEY (ATTEMPT_ID) REFERENCES SJZQ_COLLECTION_ATTEMPT(ATTEMPT_ID),
            CONSTRAINT FK_SJZQ_JOB_EVENT_DEVICE FOREIGN KEY (DEVICE_ID) REFERENCES SJZQ_DEVICE(DEVICE_ID)
        )
    """)
    _ensure_constraint(
        cur, "SJZQ_COLLECTION_JOB", "FK_SJZQ_JOB_ITEM",
        "ALTER TABLE SJZQ_COLLECTION_JOB ADD CONSTRAINT FK_SJZQ_JOB_ITEM "
        "FOREIGN KEY (TASK_ITEM_ID) REFERENCES SJZQ_TASK_ITEM(ITEM_ID)",
    )

    for sequence in (
        "SJZQ_SEQ_COLLECTION_JOB", "SJZQ_SEQ_COLLECTION_ATTEMPT", "SJZQ_SEQ_COLLECTION_LEASE",
        "SJZQ_SEQ_COLLECTION_CHECKPOINT", "SJZQ_SEQ_COLLECTION_OUTBOX", "SJZQ_SEQ_JOB_EVENT",
    ):
        _ensure_sequence(cur, sequence)
    for name, ddl in (
        ("IDX_SJZQ_TASK_DEADLINE", "CREATE INDEX IDX_SJZQ_TASK_DEADLINE ON SJZQ_TASK(DEADLINE_AT, STATUS)"),
        ("IDX_SJZQ_JOB_ACQUIRE", "CREATE INDEX IDX_SJZQ_JOB_ACQUIRE ON SJZQ_COLLECTION_JOB(STATUS, NEXT_RUN_AT, PRIORITY, TASK_ID)"),
        ("IDX_SJZQ_JOB_TASK", "CREATE INDEX IDX_SJZQ_JOB_TASK ON SJZQ_COLLECTION_JOB(TASK_ID, STATUS)"),
        ("IDX_SJZQ_JOB_LEASE_EXPIRES", "CREATE INDEX IDX_SJZQ_JOB_LEASE_EXPIRES ON SJZQ_COLLECTION_JOB(LEASE_EXPIRES_AT, STATUS)"),
        ("IDX_SJZQ_ATTEMPT_EXPIRES", "CREATE INDEX IDX_SJZQ_ATTEMPT_EXPIRES ON SJZQ_COLLECTION_ATTEMPT(LEASE_EXPIRES_AT, STATUS)"),
        ("UQ_SJZQ_ATTEMPT_ACTIVE_JOB", "CREATE UNIQUE INDEX UQ_SJZQ_ATTEMPT_ACTIVE_JOB ON SJZQ_COLLECTION_ATTEMPT (CASE WHEN STATUS IN ('leased', 'running') THEN JOB_ID ELSE NULL END)"),
        ("UQ_SJZQ_ATTEMPT_ACTIVE_DEVICE", "CREATE UNIQUE INDEX UQ_SJZQ_ATTEMPT_ACTIVE_DEVICE ON SJZQ_COLLECTION_ATTEMPT (CASE WHEN STATUS IN ('leased', 'running') THEN DEVICE_ID ELSE NULL END)"),
        ("IDX_SJZQ_LEASE_EXPIRES", "CREATE INDEX IDX_SJZQ_LEASE_EXPIRES ON SJZQ_COLLECTION_LEASE(LEASE_EXPIRES_AT, STATUS)"),
        ("IDX_SJZQ_OUTBOX_DELIVERY", "CREATE INDEX IDX_SJZQ_OUTBOX_DELIVERY ON SJZQ_COLLECTION_OUTBOX(STATUS, AVAILABLE_AT)"),
        ("IDX_SJZQ_EVENT_JOB", "CREATE INDEX IDX_SJZQ_EVENT_JOB ON SJZQ_JOB_EVENT(JOB_ID, CREATE_TIME)"),
        ("IDX_SJZQ_EVENT_TASK", "CREATE INDEX IDX_SJZQ_EVENT_TASK ON SJZQ_JOB_EVENT(TASK_ID, CREATE_TIME)"),
    ):
        _ensure_index(cur, name, ddl)


def _ensure_requirement_schema(cur) -> None:
    for table, column, ddl in [
        ("SJZQ_DEVICE", "RUN_STATE", "ALTER TABLE SJZQ_DEVICE ADD (RUN_STATE VARCHAR2(16) DEFAULT 'idle' NOT NULL)"),
        ("SJZQ_DEVICE", "RUN_STARTED_AT", "ALTER TABLE SJZQ_DEVICE ADD (RUN_STARTED_AT TIMESTAMP)"),
        ("SJZQ_DEVICE", "REST_UNTIL", "ALTER TABLE SJZQ_DEVICE ADD (REST_UNTIL TIMESTAMP)"),
        ("SJZQ_DEVICE", "MAX_CONTINUOUS_MIN", "ALTER TABLE SJZQ_DEVICE ADD (MAX_CONTINUOUS_MIN NUMBER(8) DEFAULT 120 NOT NULL)"),
        ("SJZQ_DEVICE", "MIN_REST_MIN", "ALTER TABLE SJZQ_DEVICE ADD (MIN_REST_MIN NUMBER(8) DEFAULT 30 NOT NULL)"),
        # 既有任务迁移时视为已审核，避免升级后把历史待执行任务全部卡住。
        ("SJZQ_TASK", "REVIEW_STATUS", "ALTER TABLE SJZQ_TASK ADD (REVIEW_STATUS VARCHAR2(16) DEFAULT 'approved' NOT NULL)"),
        ("SJZQ_TASK", "REVIEW_USER_ID", "ALTER TABLE SJZQ_TASK ADD (REVIEW_USER_ID NUMBER(18))"),
        ("SJZQ_TASK", "REVIEW_USERNAME", "ALTER TABLE SJZQ_TASK ADD (REVIEW_USERNAME VARCHAR2(64))"),
        ("SJZQ_TASK", "REVIEW_TIME", "ALTER TABLE SJZQ_TASK ADD (REVIEW_TIME TIMESTAMP)"),
        ("SJZQ_TASK", "REVIEW_REMARK", "ALTER TABLE SJZQ_TASK ADD (REVIEW_REMARK VARCHAR2(500))"),
        ("SJZQ_TASK_ITEM", "TARGET_NAME", "ALTER TABLE SJZQ_TASK_ITEM ADD (TARGET_NAME VARCHAR2(512))"),
        ("SJZQ_TASK_ITEM", "TARGET_MANUFACTURER", "ALTER TABLE SJZQ_TASK_ITEM ADD (TARGET_MANUFACTURER VARCHAR2(256))"),
        ("SJZQ_TASK_ITEM", "ORIGINAL_ROW_JSON", "ALTER TABLE SJZQ_TASK_ITEM ADD (ORIGINAL_ROW_JSON CLOB)"),
        ("SJZQ_PRODUCT", "LIBRARY_STATUS", "ALTER TABLE SJZQ_PRODUCT ADD (LIBRARY_STATUS VARCHAR2(16) DEFAULT 'saved' NOT NULL)"),
        ("SJZQ_PRODUCT", "IS_DELETED", "ALTER TABLE SJZQ_PRODUCT ADD (IS_DELETED NUMBER(1) DEFAULT 0 NOT NULL)"),
        ("SJZQ_PRODUCT", "SAVED_BY", "ALTER TABLE SJZQ_PRODUCT ADD (SAVED_BY NUMBER(18))"),
        ("SJZQ_PRODUCT", "SAVED_TIME", "ALTER TABLE SJZQ_PRODUCT ADD (SAVED_TIME TIMESTAMP)"),
    ]:
        _ensure_column(cur, table, column, ddl)
    cur.execute("ALTER TABLE SJZQ_TASK MODIFY (REVIEW_STATUS DEFAULT 'pending')")

    if not _object_exists(cur, "SJZQ_PLATFORM_ACCOUNT"):
        cur.execute(
            """
            CREATE TABLE SJZQ_PLATFORM_ACCOUNT (
                ACCOUNT_ID NUMBER(18) NOT NULL,
                PLATFORM_CODE VARCHAR2(32) NOT NULL,
                ACCOUNT_NAME VARCHAR2(128) NOT NULL,
                MOBILE VARCHAR2(32),
                OWNER_USER_ID NUMBER(18) NOT NULL,
                DEVICE_ID NUMBER(18),
                STATUS VARCHAR2(20) DEFAULT 'nurturing' NOT NULL,
                NURTURE_START DATE DEFAULT TRUNC(SYSDATE) NOT NULL,
                NURTURE_DAYS NUMBER(2) DEFAULT 5 NOT NULL,
                MATURE_AT DATE,
                LAST_CHECK_AT TIMESTAMP,
                BLOCK_REASON VARCHAR2(500),
                REMARK VARCHAR2(500),
                CREATE_TIME TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
                UPDATE_TIME TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
                CONSTRAINT PK_SJZQ_PLATFORM_ACCOUNT PRIMARY KEY (ACCOUNT_ID),
                CONSTRAINT UK_SJZQ_PLATFORM_ACCOUNT UNIQUE (PLATFORM_CODE, ACCOUNT_NAME)
            )
            """
        )
        print("[migrate] created SJZQ_PLATFORM_ACCOUNT")
    if not _object_exists(cur, "SJZQ_ALERT"):
        cur.execute(
            """
            CREATE TABLE SJZQ_ALERT (
                ALERT_ID NUMBER(18) NOT NULL,
                ALERT_TYPE VARCHAR2(32) NOT NULL,
                OWNER_USER_ID NUMBER(18),
                LEVEL_CODE VARCHAR2(16) DEFAULT 'warning' NOT NULL,
                MESSAGE VARCHAR2(1000) NOT NULL,
                STATUS VARCHAR2(16) DEFAULT 'unread' NOT NULL,
                CREATE_TIME TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
                ACK_TIME TIMESTAMP,
                ACK_USER_ID NUMBER(18),
                CONSTRAINT PK_SJZQ_ALERT PRIMARY KEY (ALERT_ID)
            )
            """
        )
        print("[migrate] created SJZQ_ALERT")
    _ensure_sequence(cur, "SJZQ_SEQ_PLATFORM_ACCOUNT")
    _ensure_sequence(cur, "SJZQ_SEQ_ALERT")
    if not _object_exists(cur, "SJZQ_PRODUCT_CHANGE"):
        cur.execute("""
            CREATE TABLE SJZQ_PRODUCT_CHANGE (
                CHANGE_ID NUMBER(18) NOT NULL, PRODUCT_ID NUMBER(18) NOT NULL,
                TASK_ID NUMBER(18), ACTION_CODE VARCHAR2(32) NOT NULL,
                BEFORE_JSON CLOB, AFTER_JSON CLOB, USER_ID NUMBER(18),
                USERNAME VARCHAR2(64), CREATE_TIME TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
                CONSTRAINT PK_SJZQ_PRODUCT_CHANGE PRIMARY KEY (CHANGE_ID)
            )
        """)
    if not _object_exists(cur, "SJZQ_TASK_ANOMALY"):
        cur.execute("""
            CREATE TABLE SJZQ_TASK_ANOMALY (
                ANOMALY_ID NUMBER(18) NOT NULL, TASK_ID NUMBER(18) NOT NULL,
                DEVICE_ID NUMBER(18), ACTION_NAME VARCHAR2(128), MESSAGE VARCHAR2(2000),
                PAGE_TEXT CLOB, SCREENSHOT_PATH VARCHAR2(512), CONSECUTIVE_COUNT NUMBER(8) DEFAULT 1,
                CREATE_TIME TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
                CONSTRAINT PK_SJZQ_TASK_ANOMALY PRIMARY KEY (ANOMALY_ID)
            )
        """)
    _ensure_sequence(cur, "SJZQ_SEQ_PRODUCT_CHANGE")
    _ensure_sequence(cur, "SJZQ_SEQ_TASK_ANOMALY")

    # 既有角色增量权限：运营可看/维护账号并审核本人任务；管理员拥有全部新增权限。
    role_perms = {
        "super_admin": ("account:view", "account:manage", "report:view", "task:review"),
        "operator": ("account:view", "account:manage", "report:view", "task:review"),
        "viewer": ("account:view", "report:view"),
    }
    for role_code, perms in role_perms.items():
        cur.execute("SELECT ROLE_ID FROM SJZQ_ROLE WHERE ROLE_CODE=:code", {"code": role_code})
        row = cur.fetchone()
        if not row:
            continue
        role_id = int(row[0])
        for perm in perms:
            cur.execute(
                "SELECT COUNT(*) FROM SJZQ_ROLE_PERM WHERE ROLE_ID=:rid AND PERM_CODE=:perm",
                {"rid": role_id, "perm": perm},
            )
            if int(cur.fetchone()[0] or 0) == 0:
                cur.execute(
                    "INSERT INTO SJZQ_ROLE_PERM (ROLE_ID, PERM_CODE) VALUES (:rid, :perm)",
                    {"rid": role_id, "perm": perm},
                )


def _ensure_goods_library(cur) -> None:
    """现阶段把已采集商品映射为正式库接口；已有正式表时保持原表不变。"""
    cur.execute("SELECT OBJECT_TYPE FROM USER_OBJECTS WHERE OBJECT_NAME='T_GOODS_LIBRARY'")
    row = cur.fetchone()
    if row and row[0] == "TABLE":
        return
    cur.execute(
        """
        CREATE OR REPLACE VIEW T_GOODS_LIBRARY AS
        SELECT P.PRODUCT_ID AS LIBRARY_ID,
               P.PLATFORM_CODE,
               P.ITEM_ID AS GOODS_ID,
               P.PRODUCT_NAME,
               P.SELL_NAME,
               P.SPEC_TEXT AS SPEC,
               P.APPROVAL_NO,
               P.BRAND,
               P.MANUFACTURER,
               P.PRICE AS LIST_PRICE,
               P.DEAL_PRICE AS SALE_PRICE,
               (
                   SELECT COALESCE(NULLIF(I.REL_PATH, ''), I.SOURCE_URL)
                     FROM SJZQ_PRODUCT_IMAGE I
                    WHERE I.PRODUCT_ID = P.PRODUCT_ID
                    ORDER BY I.SORT_NO, I.IMAGE_ID
                    FETCH FIRST 1 ROWS ONLY
               ) AS MAIN_IMAGE,
               P.UPDATE_TIME
               ,P.ENTERPRISE_ID
               ,P.WORKSPACE_ID
          FROM SJZQ_PRODUCT P
         WHERE NVL(P.LIBRARY_STATUS, 'saved') = 'saved' AND NVL(P.IS_DELETED, 0) = 0
        """
    )
    print("[migrate] created compatibility view T_GOODS_LIBRARY")
