"""连接 Oracle 并创建 SJZQ_ 前缀业务表。"""

from __future__ import annotations

import sys
from pathlib import Path

import oracledb

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))

from server.config import settings  # noqa: E402
from server.schema_migrations import (  # noqa: E402
    P3_INDEXES,
    P3_MIGRATION_CHECKSUM,
    P3_MIGRATION_DESCRIPTION,
    P3_MIGRATION_ID,
    P3_SEQUENCES,
    P3_TABLES,
    P4_INDEXES,
    P5_SEQUENCES,
    P5_TABLES,
    P55_INDEXES,
    P55_SEQUENCES,
    P55_TABLES,
)


DDL_STATEMENTS = [
    # ---------- 平台字典 ----------
    """
    CREATE TABLE SJZQ_PLATFORM (
        PLATFORM_CODE   VARCHAR2(32)  NOT NULL,
        PLATFORM_NAME   VARCHAR2(64)  NOT NULL,
        ENABLED         NUMBER(1)     DEFAULT 1 NOT NULL,
        SORT_NO         NUMBER(5)     DEFAULT 0 NOT NULL,
        REMARK          VARCHAR2(256),
        CREATE_TIME     TIMESTAMP     DEFAULT SYSTIMESTAMP NOT NULL,
        CONSTRAINT PK_SJZQ_PLATFORM PRIMARY KEY (PLATFORM_CODE)
    )
    """,
    # ---------- 采集设备 ----------
    """
    CREATE TABLE SJZQ_DEVICE (
        DEVICE_ID       NUMBER(18)    NOT NULL,
        DEVICE_KEY      VARCHAR2(64)  NOT NULL,
        DEVICE_NAME     VARCHAR2(128),
        PLATFORM_CODE   VARCHAR2(32)  DEFAULT 'pinduoduo' NOT NULL,
        APP_VERSION     VARCHAR2(32),
        OS_VERSION      VARCHAR2(64),
        MODEL           VARCHAR2(128),
        STATUS          VARCHAR2(16)  DEFAULT 'offline' NOT NULL,
        LAST_IP         VARCHAR2(64),
        LAST_HEARTBEAT  TIMESTAMP,
        CURRENT_TASK_ID NUMBER(18),
        ACTIVE_JOB_ID   NUMBER(18),
        ACTIVE_ATTEMPT_ID NUMBER(18),
        KEYWORD_RUN_COUNT NUMBER(18) DEFAULT 0 NOT NULL,
        REVOKED_AT      TIMESTAMP,
        REVOKED_BY      NUMBER(18),
        DEVICE_KEY_ROTATED_AT TIMESTAMP,
        ENROLLMENT_TOKEN_ID NUMBER(18),
        REMARK          VARCHAR2(256),
        CREATE_TIME     TIMESTAMP     DEFAULT SYSTIMESTAMP NOT NULL,
        UPDATE_TIME     TIMESTAMP     DEFAULT SYSTIMESTAMP NOT NULL,
        CONSTRAINT PK_SJZQ_DEVICE PRIMARY KEY (DEVICE_ID),
        CONSTRAINT UK_SJZQ_DEVICE_KEY UNIQUE (DEVICE_KEY)
    )
    """,
    # ---------- 任务主表 ----------
    """
    CREATE TABLE SJZQ_TASK (
        TASK_ID         NUMBER(18)    NOT NULL,
        TASK_NAME       VARCHAR2(128) NOT NULL,
        TASK_TYPE       VARCHAR2(32)  NOT NULL,
        PLATFORM_CODE   VARCHAR2(32)  DEFAULT 'pinduoduo' NOT NULL,
        STATUS          VARCHAR2(16)  DEFAULT 'pending' NOT NULL,
        PRIORITY        NUMBER(5)     DEFAULT 5 NOT NULL,
        DEVICE_ID       NUMBER(18),
        KEYWORD_TEXT    CLOB,
        TARGET_COUNT    NUMBER(10)    DEFAULT 0,
        SUCCESS_COUNT   NUMBER(10)    DEFAULT 0,
        FAIL_COUNT      NUMBER(10)    DEFAULT 0,
        CONFIG_JSON     CLOB,
        ERROR_MSG       VARCHAR2(1000),
        PAUSE_STATE     VARCHAR2(16)  DEFAULT 'active' NOT NULL,
        PAUSE_REQUESTED NUMBER(1)     DEFAULT 0 NOT NULL,
        DEADLINE_AT     TIMESTAMP,
        PAUSED_AT       TIMESTAMP,
        START_TIME      TIMESTAMP,
        END_TIME        TIMESTAMP,
        CREATE_TIME     TIMESTAMP     DEFAULT SYSTIMESTAMP NOT NULL,
        UPDATE_TIME     TIMESTAMP     DEFAULT SYSTIMESTAMP NOT NULL,
        CONSTRAINT PK_SJZQ_TASK PRIMARY KEY (TASK_ID)
        ,CONSTRAINT CK_SJZQ_TASK_PAUSE_STATE CHECK (PAUSE_STATE IN ('active', 'paused'))
        ,CONSTRAINT CK_SJZQ_TASK_PAUSE_REQUESTED CHECK (PAUSE_REQUESTED IN (0, 1))
    )
    """,
    # ---------- Phase 2: stable schedulable business job ----------
    """
    CREATE TABLE SJZQ_COLLECTION_JOB (
        JOB_ID              NUMBER(18)    NOT NULL,
        TASK_ID             NUMBER(18)    NOT NULL,
        TASK_ITEM_ID        NUMBER(18),
        DEVICE_ID           NUMBER(18),
        JOB_KEY             VARCHAR2(256) NOT NULL,
        JOB_TYPE            VARCHAR2(32)  NOT NULL,
        TARGET_JSON         CLOB,
        STATUS              VARCHAR2(16)  DEFAULT 'pending' NOT NULL,
        PRIORITY            NUMBER(5)     DEFAULT 5 NOT NULL,
        MAX_ATTEMPTS        NUMBER(5)     DEFAULT 5 NOT NULL,
        ATTEMPT_COUNT       NUMBER(5)     DEFAULT 0 NOT NULL,
        NEXT_RUN_AT         TIMESTAMP     DEFAULT SYSTIMESTAMP NOT NULL,
        ACTIVE_ATTEMPT_ID   NUMBER(18),
        LEASE_TOKEN_HASH    VARCHAR2(64),
        LEASED_AT           TIMESTAMP,
        LEASE_EXPIRES_AT    TIMESTAMP,
        LAST_HEARTBEAT_AT   TIMESTAMP,
        CHECKPOINT_VERSION  NUMBER(10)    DEFAULT 0 NOT NULL,
        CHECKPOINT_JSON     CLOB,
        RESULT_RECEIPT_KEY  VARCHAR2(128),
        RESULT_PRODUCT_ID   NUMBER(18),
        PAUSE_REQUESTED     NUMBER(1)     DEFAULT 0 NOT NULL,
        LAST_ERROR_CLASS    VARCHAR2(48),
        LAST_ERROR_CODE     VARCHAR2(128),
        LAST_ERROR_MESSAGE  VARCHAR2(2000),
        CREATE_TIME         TIMESTAMP     DEFAULT SYSTIMESTAMP NOT NULL,
        UPDATE_TIME         TIMESTAMP     DEFAULT SYSTIMESTAMP NOT NULL,
        CONSTRAINT PK_SJZQ_COLLECTION_JOB PRIMARY KEY (JOB_ID),
        CONSTRAINT UK_SJZQ_COLLECTION_JOB_KEY UNIQUE (JOB_KEY),
        CONSTRAINT CK_SJZQ_JOB_STATUS CHECK (STATUS IN
            ('pending', 'leased', 'running', 'paused', 'retry_wait', 'success',
             'failed', 'cancelled', 'dead', 'quarantined')),
        CONSTRAINT CK_SJZQ_JOB_ATTEMPTS CHECK (MAX_ATTEMPTS >= 1 AND ATTEMPT_COUNT >= 0),
        CONSTRAINT CK_SJZQ_JOB_PAUSE_REQUESTED CHECK (PAUSE_REQUESTED IN (0, 1)),
        CONSTRAINT FK_SJZQ_JOB_TASK FOREIGN KEY (TASK_ID) REFERENCES SJZQ_TASK(TASK_ID),
        CONSTRAINT FK_SJZQ_JOB_DEVICE FOREIGN KEY (DEVICE_ID) REFERENCES SJZQ_DEVICE(DEVICE_ID)
    )
    """,
    # ---------- Phase 2: immutable execution attempt history ----------
    """
    CREATE TABLE SJZQ_COLLECTION_ATTEMPT (
        ATTEMPT_ID             NUMBER(18)    NOT NULL,
        JOB_ID                 NUMBER(18)    NOT NULL,
        ATTEMPT_NO             NUMBER(5)     NOT NULL,
        DEVICE_ID              NUMBER(18),
        WORKER_ID              VARCHAR2(128),
        LEASE_TOKEN_HASH       VARCHAR2(64)  NOT NULL,
        TRACE_ID               VARCHAR2(128) NOT NULL,
        STATUS                 VARCHAR2(16)  DEFAULT 'leased' NOT NULL,
        LEASED_AT              TIMESTAMP     DEFAULT SYSTIMESTAMP NOT NULL,
        STARTED_AT             TIMESTAMP,
        HEARTBEAT_AT           TIMESTAMP,
        LEASE_EXPIRES_AT       TIMESTAMP     NOT NULL,
        FINISHED_AT            TIMESTAMP,
        ERROR_CLASS            VARCHAR2(48),
        ERROR_CODE             VARCHAR2(128),
        ERROR_MESSAGE          VARCHAR2(2000),
        RETRYABLE              NUMBER(1),
        RETRY_DELAY_SECONDS    NUMBER(10),
        START_CHECKPOINT_VERSION NUMBER(10)  DEFAULT 0 NOT NULL,
        FINAL_CHECKPOINT_VERSION NUMBER(10),
        CREATE_TIME            TIMESTAMP     DEFAULT SYSTIMESTAMP NOT NULL,
        CONSTRAINT PK_SJZQ_COLLECTION_ATTEMPT PRIMARY KEY (ATTEMPT_ID),
        CONSTRAINT UK_SJZQ_ATTEMPT_NO UNIQUE (JOB_ID, ATTEMPT_NO),
        CONSTRAINT UK_SJZQ_ATTEMPT_LEASE_TOKEN UNIQUE (LEASE_TOKEN_HASH),
        CONSTRAINT CK_SJZQ_ATTEMPT_STATUS CHECK (STATUS IN
            ('leased', 'running', 'success', 'failed', 'timeout', 'cancelled', 'reclaimed')),
        CONSTRAINT CK_SJZQ_ATTEMPT_RETRYABLE CHECK (RETRYABLE IN (0, 1) OR RETRYABLE IS NULL),
        CONSTRAINT CK_SJZQ_ATTEMPT_NUMBERS CHECK
            (ATTEMPT_NO >= 1 AND START_CHECKPOINT_VERSION >= 0
             AND (FINAL_CHECKPOINT_VERSION IS NULL OR FINAL_CHECKPOINT_VERSION >= 0)),
        CONSTRAINT FK_SJZQ_ATTEMPT_JOB FOREIGN KEY (JOB_ID) REFERENCES SJZQ_COLLECTION_JOB(JOB_ID),
        CONSTRAINT FK_SJZQ_ATTEMPT_DEVICE FOREIGN KEY (DEVICE_ID) REFERENCES SJZQ_DEVICE(DEVICE_ID)
    )
    """,
    # Lease mirrors an Attempt in the same transactional state change. The
    # scheduler validates Job + Attempt first; this table makes lease history
    # and release/reclaim causes queryable without creating a second owner.
    """
    CREATE TABLE SJZQ_COLLECTION_LEASE (
        LEASE_ID             NUMBER(18)    NOT NULL,
        JOB_ID               NUMBER(18)    NOT NULL,
        ATTEMPT_ID           NUMBER(18)    NOT NULL,
        DEVICE_ID            NUMBER(18),
        WORKER_ID            VARCHAR2(128),
        LEASE_TOKEN_HASH     VARCHAR2(64)  NOT NULL,
        STATUS               VARCHAR2(16)  DEFAULT 'active' NOT NULL,
        LEASED_AT            TIMESTAMP     NOT NULL,
        LEASE_EXPIRES_AT     TIMESTAMP     NOT NULL,
        HEARTBEAT_AT         TIMESTAMP,
        RELEASED_AT          TIMESTAMP,
        RECLAIMED_AT         TIMESTAMP,
        RELEASE_REASON       VARCHAR2(128),
        CREATE_TIME          TIMESTAMP     DEFAULT SYSTIMESTAMP NOT NULL,
        CONSTRAINT PK_SJZQ_COLLECTION_LEASE PRIMARY KEY (LEASE_ID),
        CONSTRAINT UK_SJZQ_LEASE_ATTEMPT UNIQUE (ATTEMPT_ID),
        CONSTRAINT UK_SJZQ_COLLECTION_LEASE_TOKEN UNIQUE (LEASE_TOKEN_HASH),
        CONSTRAINT CK_SJZQ_LEASE_STATUS CHECK (STATUS IN ('active', 'released', 'reclaimed', 'expired')),
        CONSTRAINT CK_SJZQ_COLLECTION_LEASE_DATES CHECK (LEASE_EXPIRES_AT >= LEASED_AT),
        CONSTRAINT FK_SJZQ_COLLECTION_LEASE_JOB FOREIGN KEY (JOB_ID) REFERENCES SJZQ_COLLECTION_JOB(JOB_ID),
        CONSTRAINT FK_SJZQ_LEASE_ATTEMPT FOREIGN KEY (ATTEMPT_ID) REFERENCES SJZQ_COLLECTION_ATTEMPT(ATTEMPT_ID),
        CONSTRAINT FK_SJZQ_LEASE_DEVICE FOREIGN KEY (DEVICE_ID) REFERENCES SJZQ_DEVICE(DEVICE_ID)
    )
    """,
    # ---------- Phase 2: server-confirmed checkpoint receipt/history ----------
    """
    CREATE TABLE SJZQ_COLLECTION_CHECKPOINT (
        CHECKPOINT_ID       NUMBER(18)    NOT NULL,
        JOB_ID              NUMBER(18)    NOT NULL,
        ATTEMPT_ID          NUMBER(18),
        VERSION             NUMBER(10)    NOT NULL,
        IDEMPOTENCY_KEY     VARCHAR2(128) NOT NULL,
        PAYLOAD_SHA256      VARCHAR2(64)  NOT NULL,
        PAYLOAD_JSON        CLOB          NOT NULL,
        CREATE_TIME         TIMESTAMP     DEFAULT SYSTIMESTAMP NOT NULL,
        CONSTRAINT PK_SJZQ_COLLECTION_CHECKPOINT PRIMARY KEY (CHECKPOINT_ID),
        CONSTRAINT UK_SJZQ_CKPT_JOB_VER UNIQUE (JOB_ID, VERSION),
        CONSTRAINT UK_SJZQ_CKPT_JOB_IDEM UNIQUE (JOB_ID, IDEMPOTENCY_KEY),
        CONSTRAINT CK_SJZQ_CKPT_VERSION CHECK (VERSION >= 1),
        CONSTRAINT FK_SJZQ_CHECKPOINT_JOB FOREIGN KEY (JOB_ID) REFERENCES SJZQ_COLLECTION_JOB(JOB_ID),
        CONSTRAINT FK_SJZQ_CHECKPOINT_ATTEMPT FOREIGN KEY (ATTEMPT_ID) REFERENCES SJZQ_COLLECTION_ATTEMPT(ATTEMPT_ID)
    )
    """,
    # ---------- Phase 2: transactional server outbox ----------
    """
    CREATE TABLE SJZQ_COLLECTION_OUTBOX (
        OUTBOX_ID           NUMBER(18)    NOT NULL,
        EVENT_KEY           VARCHAR2(128) NOT NULL,
        EVENT_TYPE          VARCHAR2(64)  NOT NULL,
        AGGREGATE_TYPE      VARCHAR2(32)  NOT NULL,
        TASK_ID             NUMBER(18),
        JOB_ID              NUMBER(18),
        ATTEMPT_ID          NUMBER(18),
        PAYLOAD_JSON        CLOB          NOT NULL,
        STATUS              VARCHAR2(16)  DEFAULT 'pending' NOT NULL,
        AVAILABLE_AT        TIMESTAMP     DEFAULT SYSTIMESTAMP NOT NULL,
        DELIVERY_ATTEMPTS   NUMBER(10)    DEFAULT 0 NOT NULL,
        LOCK_TOKEN          VARCHAR2(128),
        LOCKED_AT           TIMESTAMP,
        LOCK_EXPIRES_AT     TIMESTAMP,
        LAST_ERROR_CODE     VARCHAR2(128),
        LAST_ERROR_MESSAGE  VARCHAR2(2000),
        PUBLISHED_AT        TIMESTAMP,
        CREATE_TIME         TIMESTAMP     DEFAULT SYSTIMESTAMP NOT NULL,
        UPDATE_TIME         TIMESTAMP     DEFAULT SYSTIMESTAMP NOT NULL,
        CONSTRAINT PK_SJZQ_COLLECTION_OUTBOX PRIMARY KEY (OUTBOX_ID),
        CONSTRAINT UK_SJZQ_OUTBOX_EVENT UNIQUE (EVENT_KEY),
        CONSTRAINT CK_SJZQ_OUTBOX_STATUS CHECK (STATUS IN ('pending', 'leased', 'delivered', 'dead')),
        CONSTRAINT CK_SJZQ_OUTBOX_ATTEMPTS CHECK (DELIVERY_ATTEMPTS >= 0),
        CONSTRAINT FK_SJZQ_OUTBOX_TASK FOREIGN KEY (TASK_ID) REFERENCES SJZQ_TASK(TASK_ID),
        CONSTRAINT FK_SJZQ_OUTBOX_JOB FOREIGN KEY (JOB_ID) REFERENCES SJZQ_COLLECTION_JOB(JOB_ID),
        CONSTRAINT FK_SJZQ_OUTBOX_ATTEMPT FOREIGN KEY (ATTEMPT_ID) REFERENCES SJZQ_COLLECTION_ATTEMPT(ATTEMPT_ID)
    )
    """,
    # ---------- Phase 2: append-only structured execution trace ----------
    """
    CREATE TABLE SJZQ_JOB_EVENT (
        EVENT_ID            NUMBER(18)    NOT NULL,
        EVENT_KEY           VARCHAR2(128) NOT NULL,
        TASK_ID             NUMBER(18),
        JOB_ID              NUMBER(18),
        ATTEMPT_ID          NUMBER(18),
        DEVICE_ID           NUMBER(18),
        WORKER_ID           VARCHAR2(128),
        LEASE_TOKEN_HASH    VARCHAR2(64),
        TRACE_ID            VARCHAR2(128),
        EVENT_TYPE          VARCHAR2(64)  NOT NULL,
        OLD_STATUS          VARCHAR2(16),
        NEW_STATUS          VARCHAR2(16),
        ERROR_CLASS         VARCHAR2(48),
        ERROR_CODE          VARCHAR2(128),
        DETAIL_JSON         CLOB,
        CREATE_TIME         TIMESTAMP     DEFAULT SYSTIMESTAMP NOT NULL,
        CONSTRAINT PK_SJZQ_JOB_EVENT PRIMARY KEY (EVENT_ID),
        CONSTRAINT UK_SJZQ_JOB_EVENT_KEY UNIQUE (EVENT_KEY),
        CONSTRAINT FK_SJZQ_JOB_EVENT_TASK FOREIGN KEY (TASK_ID) REFERENCES SJZQ_TASK(TASK_ID),
        CONSTRAINT FK_SJZQ_JOB_EVENT_JOB FOREIGN KEY (JOB_ID) REFERENCES SJZQ_COLLECTION_JOB(JOB_ID),
        CONSTRAINT FK_SJZQ_JOB_EVENT_ATTEMPT FOREIGN KEY (ATTEMPT_ID) REFERENCES SJZQ_COLLECTION_ATTEMPT(ATTEMPT_ID),
        CONSTRAINT FK_SJZQ_JOB_EVENT_DEVICE FOREIGN KEY (DEVICE_ID) REFERENCES SJZQ_DEVICE(DEVICE_ID)
    )
    """,
    # ---------- 任务明细（关键词/目标行） ----------
    """
    CREATE TABLE SJZQ_TASK_ITEM (
        ITEM_ID         NUMBER(18)    NOT NULL,
        TASK_ID         NUMBER(18)    NOT NULL,
        ROW_INDEX       NUMBER(10)    DEFAULT 0 NOT NULL,
        KEYWORD         VARCHAR2(256) NOT NULL,
        TARGET_SPEC     VARCHAR2(256),
        TARGET_APPROVAL VARCHAR2(128),
        STATUS          VARCHAR2(16)  DEFAULT 'pending' NOT NULL,
        PRODUCT_ID      NUMBER(18),
        MESSAGE         VARCHAR2(1000),
        UPDATE_TIME     TIMESTAMP     DEFAULT SYSTIMESTAMP NOT NULL,
        CONSTRAINT PK_SJZQ_TASK_ITEM PRIMARY KEY (ITEM_ID)
    )
    """,
    # ---------- 任务运行日志 ----------
    """
    CREATE TABLE SJZQ_TASK_LOG (
        LOG_ID          NUMBER(18)    NOT NULL,
        TASK_ID         NUMBER(18)    NOT NULL,
        DEVICE_ID       NUMBER(18),
        LEVEL_CODE      VARCHAR2(16)  DEFAULT 'info' NOT NULL,
        MESSAGE         VARCHAR2(2000) NOT NULL,
        CREATE_TIME     TIMESTAMP     DEFAULT SYSTIMESTAMP NOT NULL,
        CONSTRAINT PK_SJZQ_TASK_LOG PRIMARY KEY (LOG_ID)
    )
    """,
    # ---------- Progress delta replay receipts ----------
    """
    CREATE TABLE SJZQ_PROGRESS_RECEIPT (
        PROGRESS_ID     VARCHAR2(64) NOT NULL,
        TASK_ID        NUMBER(18) NOT NULL,
        DEVICE_ID      NUMBER(18) NOT NULL,
        CREATE_TIME    TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
        CONSTRAINT PK_SJZQ_PROGRESS_RECEIPT PRIMARY KEY (PROGRESS_ID)
    )
    """,
    # ---------- Reliable Agent upload receipts ----------
    """
    CREATE TABLE SJZQ_UPLOAD_RECEIPT (
        IDEMPOTENCY_KEY VARCHAR2(128) NOT NULL,
        TASK_ID        NUMBER(18),
        DEVICE_ID      NUMBER(18) NOT NULL,
        OP_TYPE        VARCHAR2(16) NOT NULL,
        PAYLOAD_SHA256 VARCHAR2(64) NOT NULL,
        PRODUCT_ID     NUMBER(18),
        MASTER_PRODUCT_ID NUMBER(18),
        SNAPSHOT_ID    NUMBER(18),
        QUARANTINE_ID  NUMBER(18),
        RESULT_JSON    CLOB,
        STATUS         VARCHAR2(16) DEFAULT 'acked' NOT NULL,
        CREATE_TIME    TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
        ACK_TIME       TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
        CONSTRAINT PK_SJZQ_UPLOAD_RECEIPT PRIMARY KEY (IDEMPOTENCY_KEY)
    )
    """,
    # ---------- 商品主表 ----------
    """
    CREATE TABLE SJZQ_PRODUCT (
        PRODUCT_ID      NUMBER(18)    NOT NULL,
        MASTER_PRODUCT_ID NUMBER(18),
        SNAPSHOT_ID     NUMBER(18),
        TASK_ID         NUMBER(18),
        DEVICE_ID       NUMBER(18),
        PLATFORM_CODE   VARCHAR2(32)  DEFAULT 'pinduoduo' NOT NULL,
        KEYWORD         VARCHAR2(256),
        ITEM_ID         VARCHAR2(64),
        SELL_NAME       VARCHAR2(512),
        PRODUCT_NAME    VARCHAR2(512),
        BRAND           VARCHAR2(128),
        SHOP_NAME       VARCHAR2(256),
        SHOP_ID         VARCHAR2(64),
        PRICE           NUMBER(18,4),
        DISPLAY_PRICE   NUMBER(18,4),
        GROUP_PRICE     NUMBER(18,4),
        DEAL_PRICE      NUMBER(18,4),
        ORIGINAL_PRICE  NUMBER(18,4),
        SALES_NUM       NUMBER(12),
        SHOP_SALES_NUM  NUMBER(12),
        COMMENT_NUM     NUMBER(12),
        SPEC_TEXT       VARCHAR2(512),
        SKU_PRICES_TEXT VARCHAR2(2000),
        SKU_PRICES_JSON CLOB,
        DOSAGE_FORM     VARCHAR2(128),
        APPROVAL_NO     VARCHAR2(128),
        MANUFACTURER    VARCHAR2(256),
        EXPIRY_TEXT     VARCHAR2(128),
        CATEGORY        VARCHAR2(256),
        COUPON_INFO     VARCHAR2(512),
        ITEM_URL        VARCHAR2(1000),
        PICK_TAG        VARCHAR2(64),
        SPEC_LIST       CLOB,
        RAW_JSON        CLOB,
        PARSE_STATUS    VARCHAR2(16),
        PAGE_STATUS     VARCHAR2(32),
        QUALITY_STATUS  VARCHAR2(16),
        FIELD_SOURCES   CLOB,
        PARSER_VERSION  VARCHAR2(64),
        QUALITY_RULES_VERSION VARCHAR2(64),
        COLLECT_TIME    TIMESTAMP     DEFAULT SYSTIMESTAMP NOT NULL,
        CREATE_TIME     TIMESTAMP     DEFAULT SYSTIMESTAMP NOT NULL,
        UPDATE_TIME     TIMESTAMP     DEFAULT SYSTIMESTAMP NOT NULL,
        CONSTRAINT PK_SJZQ_PRODUCT PRIMARY KEY (PRODUCT_ID)
    )
    """,
    # ---------- 商品图片（文件落本地磁盘，表存路径） ----------
    """
    CREATE TABLE SJZQ_PRODUCT_IMAGE (
        IMAGE_ID        NUMBER(18)    NOT NULL,
        PRODUCT_ID      NUMBER(18)    NOT NULL,
        PLATFORM_CODE   VARCHAR2(32)  DEFAULT 'pinduoduo' NOT NULL,
        SORT_NO         NUMBER(5)     DEFAULT 0 NOT NULL,
        FILE_NAME       VARCHAR2(256) NOT NULL,
        REL_PATH        VARCHAR2(512),
        SOURCE_URL      VARCHAR2(1000),
        FILE_SIZE       NUMBER(18),
        CONTENT_TYPE    VARCHAR2(64),
        CREATE_TIME     TIMESTAMP     DEFAULT SYSTIMESTAMP NOT NULL,
        CONSTRAINT PK_SJZQ_PRODUCT_IMAGE PRIMARY KEY (IMAGE_ID)
    )
    """,
]

# Phase 3 clean-init declarations include SJZQ_SCHEMA_MIGRATION,
# SJZQ_PRODUCT_MASTER, SJZQ_RAW_COLLECTION, SJZQ_PRODUCT_SNAPSHOT,
# SJZQ_FIELD_PROVENANCE, SJZQ_QUALITY_RESULT, SJZQ_DATA_QUARANTINE, and
# SJZQ_SNAPSHOT_DIFF.  The canonical DDL lives beside the versioned migration
# so an empty database and an upgraded database receive identical objects.
DDL_STATEMENTS.extend(ddl for _, ddl in P3_TABLES)
DDL_STATEMENTS.extend(ddl for _, ddl in P5_TABLES)
DDL_STATEMENTS.extend(ddl for _, ddl in P55_TABLES)

SEQUENCES = [
    "SJZQ_SEQ_DEVICE",
    "SJZQ_SEQ_TASK",
    "SJZQ_SEQ_TASK_ITEM",
    "SJZQ_SEQ_TASK_LOG",
    "SJZQ_SEQ_PRODUCT",
    "SJZQ_SEQ_PRODUCT_IMAGE",
    "SJZQ_SEQ_COLLECTION_JOB",
    "SJZQ_SEQ_COLLECTION_ATTEMPT",
    "SJZQ_SEQ_COLLECTION_LEASE",
    "SJZQ_SEQ_COLLECTION_CHECKPOINT",
    "SJZQ_SEQ_COLLECTION_OUTBOX",
    "SJZQ_SEQ_JOB_EVENT",
    *P3_SEQUENCES,
    *P5_SEQUENCES,
    *P55_SEQUENCES,
]

INDEXES = [
    "CREATE INDEX IDX_SJZQ_DEVICE_STATUS ON SJZQ_DEVICE(STATUS)",
    "CREATE INDEX IDX_SJZQ_DEVICE_PLATFORM ON SJZQ_DEVICE(PLATFORM_CODE)",
    "CREATE INDEX IDX_SJZQ_TASK_STATUS ON SJZQ_TASK(STATUS, PRIORITY)",
    "CREATE INDEX IDX_SJZQ_TASK_DEADLINE ON SJZQ_TASK(DEADLINE_AT, STATUS)",
    "CREATE INDEX IDX_SJZQ_TASK_PLATFORM ON SJZQ_TASK(PLATFORM_CODE)",
    "CREATE INDEX IDX_SJZQ_TASK_DEVICE ON SJZQ_TASK(DEVICE_ID)",
    "CREATE INDEX IDX_SJZQ_TASK_ITEM_TASK ON SJZQ_TASK_ITEM(TASK_ID, STATUS)",
    "CREATE INDEX IDX_SJZQ_TASK_LOG_TASK ON SJZQ_TASK_LOG(TASK_ID)",
    "CREATE INDEX IDX_SJZQ_PRODUCT_TASK ON SJZQ_PRODUCT(TASK_ID)",
    "CREATE INDEX IDX_SJZQ_PRODUCT_PLATFORM ON SJZQ_PRODUCT(PLATFORM_CODE, ITEM_ID)",
    "CREATE INDEX IDX_SJZQ_PRODUCT_KEYWORD ON SJZQ_PRODUCT(KEYWORD)",
    "CREATE INDEX IDX_SJZQ_PRODUCT_APPROVAL ON SJZQ_PRODUCT(APPROVAL_NO)",
    "CREATE INDEX IDX_SJZQ_RECEIPT_TASK ON SJZQ_UPLOAD_RECEIPT(TASK_ID, OP_TYPE, STATUS)",
    "CREATE INDEX IDX_SJZQ_IMG_PRODUCT ON SJZQ_PRODUCT_IMAGE(PRODUCT_ID)",
    "CREATE INDEX IDX_SJZQ_JOB_ACQUIRE ON SJZQ_COLLECTION_JOB(STATUS, NEXT_RUN_AT, PRIORITY, TASK_ID)",
    "CREATE INDEX IDX_SJZQ_JOB_TASK ON SJZQ_COLLECTION_JOB(TASK_ID, STATUS)",
    "CREATE INDEX IDX_SJZQ_JOB_LEASE_EXPIRES ON SJZQ_COLLECTION_JOB(LEASE_EXPIRES_AT, STATUS)",
    "CREATE INDEX IDX_SJZQ_ATTEMPT_EXPIRES ON SJZQ_COLLECTION_ATTEMPT(LEASE_EXPIRES_AT, STATUS)",
    "CREATE UNIQUE INDEX UQ_SJZQ_ATTEMPT_ACTIVE_JOB ON SJZQ_COLLECTION_ATTEMPT (CASE WHEN STATUS IN ('leased', 'running') THEN JOB_ID ELSE NULL END)",
    "CREATE UNIQUE INDEX UQ_SJZQ_ATTEMPT_ACTIVE_DEVICE ON SJZQ_COLLECTION_ATTEMPT (CASE WHEN STATUS IN ('leased', 'running') THEN DEVICE_ID ELSE NULL END)",
    "CREATE INDEX IDX_SJZQ_LEASE_EXPIRES ON SJZQ_COLLECTION_LEASE(LEASE_EXPIRES_AT, STATUS)",
    "CREATE INDEX IDX_SJZQ_OUTBOX_DELIVERY ON SJZQ_COLLECTION_OUTBOX(STATUS, AVAILABLE_AT)",
    "CREATE INDEX IDX_SJZQ_EVENT_JOB ON SJZQ_JOB_EVENT(JOB_ID, CREATE_TIME)",
    "CREATE INDEX IDX_SJZQ_EVENT_TASK ON SJZQ_JOB_EVENT(TASK_ID, CREATE_TIME)",
    *(ddl for _, ddl in P3_INDEXES),
    *(ddl for _, ddl in P4_INDEXES),
    *(ddl for _, ddl in P55_INDEXES),
]

# TASK_ITEM is defined after the Phase 2 tables in DDL_STATEMENTS for legacy
# readability.  Add this foreign key only after all tables exist; migration
# installs the equivalent constraint as part of the atomic new-table DDL.
POST_DDL_CONSTRAINTS = [
    (
        "SJZQ_COLLECTION_JOB",
        "FK_SJZQ_JOB_ITEM",
        "ALTER TABLE SJZQ_COLLECTION_JOB ADD CONSTRAINT FK_SJZQ_JOB_ITEM "
        "FOREIGN KEY (TASK_ITEM_ID) REFERENCES SJZQ_TASK_ITEM(ITEM_ID)",
    ),
]

PLATFORM_SEED = [
    ("pinduoduo", "拼多多", 1, 10, "当前已接入"),
    ("tmall", "天猫", 0, 20, "预留"),
    ("jd", "京东", 0, 30, "预留"),
    ("douyin", "抖音", 0, 40, "预留"),
]


def _exists_table(cur: oracledb.Cursor, name: str) -> bool:
    cur.execute(
        "SELECT COUNT(*) FROM user_tables WHERE table_name = :n",
        {"n": name.upper()},
    )
    return int(cur.fetchone()[0]) > 0


def _exists_seq(cur: oracledb.Cursor, name: str) -> bool:
    cur.execute(
        "SELECT COUNT(*) FROM user_sequences WHERE sequence_name = :n",
        {"n": name.upper()},
    )
    return int(cur.fetchone()[0]) > 0


def _exists_constraint(cur: oracledb.Cursor, table: str, name: str) -> bool:
    cur.execute(
        "SELECT COUNT(*) FROM user_constraints WHERE table_name=:t AND constraint_name=:n",
        {"t": table.upper(), "n": name.upper()},
    )
    return int(cur.fetchone()[0]) > 0


def init_schema(drop_existing: bool = False) -> None:
    dsn = settings.oracle_dsn
    print(f"Connecting {settings.oracle_user}@{dsn} ...")
    conn = oracledb.connect(
        user=settings.oracle_user,
        password=settings.oracle_password.get_secret_value(),
        dsn=dsn,
    )
    cur = conn.cursor()
    try:
        cur.execute("SELECT banner FROM v$version WHERE ROWNUM = 1")
        print("DB:", cur.fetchone()[0])

        if drop_existing:
            for t in [
                "SJZQ_FIELD_PROVENANCE",
                "SJZQ_QUALITY_RESULT",
                "SJZQ_DATA_QUARANTINE",
                "SJZQ_SNAPSHOT_DIFF",
                "SJZQ_PRODUCT_SNAPSHOT",
                "SJZQ_RAW_COLLECTION",
                "SJZQ_PRODUCT_MASTER",
                "SJZQ_SCHEMA_MIGRATION",
                "SJZQ_JOB_EVENT",
                "SJZQ_COLLECTION_OUTBOX",
                "SJZQ_COLLECTION_CHECKPOINT",
                "SJZQ_COLLECTION_LEASE",
                "SJZQ_COLLECTION_ATTEMPT",
                "SJZQ_COLLECTION_JOB",
                "SJZQ_PRODUCT_IMAGE",
                "SJZQ_PRODUCT",
                "SJZQ_TASK_LOG",
                "SJZQ_UPLOAD_RECEIPT",
                "SJZQ_PROGRESS_RECEIPT",
                "SJZQ_TASK_ITEM",
                "SJZQ_TASK",
                "SJZQ_DEVICE",
                "SJZQ_PLATFORM",
            ]:
                if _exists_table(cur, t):
                    cur.execute(f"DROP TABLE {t} CASCADE CONSTRAINTS")
                    print("DROP TABLE", t)
            for s in SEQUENCES:
                if _exists_seq(cur, s):
                    cur.execute(f"DROP SEQUENCE {s}")
                    print("DROP SEQUENCE", s)
            conn.commit()

        for ddl in DDL_STATEMENTS:
            table = ddl.split("CREATE TABLE")[1].split("(")[0].strip()
            if _exists_table(cur, table):
                print("SKIP TABLE", table)
                continue
            cur.execute(ddl)
            print("CREATE TABLE", table)

        for table, name, ddl in POST_DDL_CONSTRAINTS:
            if _exists_constraint(cur, table, name):
                print("SKIP CONSTRAINT", name)
                continue
            cur.execute(ddl)
            print("CREATE CONSTRAINT", name)

        for seq in SEQUENCES:
            if _exists_seq(cur, seq):
                print("SKIP SEQUENCE", seq)
                continue
            cur.execute(f"CREATE SEQUENCE {seq} START WITH 1 INCREMENT BY 1 NOCACHE")
            print("CREATE SEQUENCE", seq)

        for idx in INDEXES:
            name = idx.split("INDEX")[1].split("ON")[0].strip()
            cur.execute(
                "SELECT COUNT(*) FROM user_indexes WHERE index_name = :n",
                {"n": name.upper()},
            )
            if int(cur.fetchone()[0]) > 0:
                print("SKIP INDEX", name)
                continue
            try:
                cur.execute(idx)
                print("CREATE INDEX", name)
            except oracledb.DatabaseError as e:
                print("INDEX WARN", name, e)

        for code, name, enabled, sort_no, remark in PLATFORM_SEED:
            cur.execute(
                "SELECT COUNT(*) FROM SJZQ_PLATFORM WHERE PLATFORM_CODE = :c",
                {"c": code},
            )
            if int(cur.fetchone()[0]) == 0:
                cur.execute(
                    """
                    INSERT INTO SJZQ_PLATFORM
                    (PLATFORM_CODE, PLATFORM_NAME, ENABLED, SORT_NO, REMARK)
                    VALUES (:c, :n, :e, :s, :r)
                    """,
                    {"c": code, "n": name, "e": enabled, "s": sort_no, "r": remark},
                )
                print("SEED PLATFORM", code)
            else:
                print("SKIP PLATFORM", code)

        # A clean init installs the current schema in one pass, so record the
        # released Phase 3 migration as applied.  Existing migration rows are
        # immutable apart from lifecycle timestamps/status; a checksum mismatch
        # signals edited migration history rather than silently accepting it.
        cur.execute(
            "SELECT CHECKSUM FROM SJZQ_SCHEMA_MIGRATION WHERE VERSION_ID=:version_id",
            {"version_id": P3_MIGRATION_ID},
        )
        row = cur.fetchone()
        if row is None:
            cur.execute(
                """
                INSERT INTO SJZQ_SCHEMA_MIGRATION
                (VERSION_ID, CHECKSUM, DESCRIPTION, STATUS, STARTED_AT, APPLIED_AT)
                VALUES (:version_id, :checksum, :description, 'applied', SYSTIMESTAMP, SYSTIMESTAMP)
                """,
                {
                    "version_id": P3_MIGRATION_ID,
                    "checksum": P3_MIGRATION_CHECKSUM,
                    "description": P3_MIGRATION_DESCRIPTION,
                },
            )
            print("RECORD MIGRATION", P3_MIGRATION_ID)
        elif str(row[0]) != P3_MIGRATION_CHECKSUM:
            raise RuntimeError(f"migration checksum mismatch: {P3_MIGRATION_ID}")

        conn.commit()
        cur.execute(
            "SELECT table_name FROM user_tables WHERE table_name LIKE 'SJZQ_%' ORDER BY 1"
        )
        print("TABLES:", [r[0] for r in cur.fetchall()])
        print("OK")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    drop = "--drop" in sys.argv
    init_schema(drop_existing=drop)
