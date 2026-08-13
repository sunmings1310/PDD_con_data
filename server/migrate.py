"""Lightweight schema patches applied on server startup."""
from __future__ import annotations

from server.db import get_conn


def ensure_schema_patches() -> None:
    with get_conn() as conn:
        cur = conn.cursor()
        _ensure_column(
            cur,
            table="SJZQ_DEVICE",
            column="KEYWORD_RUN_COUNT",
            ddl="ALTER TABLE SJZQ_DEVICE ADD (KEYWORD_RUN_COUNT NUMBER(18) DEFAULT 0 NOT NULL)",
        )
        _ensure_requirement_schema(cur)
        _ensure_goods_library(cur)


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
          FROM SJZQ_PRODUCT P
         WHERE NVL(P.LIBRARY_STATUS, 'saved') = 'saved' AND NVL(P.IS_DELETED, 0) = 0
        """
    )
    print("[migrate] created compatibility view T_GOODS_LIBRARY")
