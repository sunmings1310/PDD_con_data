"""连接 Oracle 并创建 SJZQ_ 前缀业务表。"""

from __future__ import annotations

import sys
from pathlib import Path

import oracledb

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))

from server.config import settings  # noqa: E402


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
        KEYWORD_RUN_COUNT NUMBER(18) DEFAULT 0 NOT NULL,
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
        START_TIME      TIMESTAMP,
        END_TIME        TIMESTAMP,
        CREATE_TIME     TIMESTAMP     DEFAULT SYSTIMESTAMP NOT NULL,
        UPDATE_TIME     TIMESTAMP     DEFAULT SYSTIMESTAMP NOT NULL,
        CONSTRAINT PK_SJZQ_TASK PRIMARY KEY (TASK_ID)
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
    # ---------- 商品主表 ----------
    """
    CREATE TABLE SJZQ_PRODUCT (
        PRODUCT_ID      NUMBER(18)    NOT NULL,
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
        REL_PATH        VARCHAR2(512) NOT NULL,
        SOURCE_URL      VARCHAR2(1000),
        FILE_SIZE       NUMBER(18),
        CONTENT_TYPE    VARCHAR2(64),
        CREATE_TIME     TIMESTAMP     DEFAULT SYSTIMESTAMP NOT NULL,
        CONSTRAINT PK_SJZQ_PRODUCT_IMAGE PRIMARY KEY (IMAGE_ID)
    )
    """,
]

SEQUENCES = [
    "SJZQ_SEQ_DEVICE",
    "SJZQ_SEQ_TASK",
    "SJZQ_SEQ_TASK_ITEM",
    "SJZQ_SEQ_TASK_LOG",
    "SJZQ_SEQ_PRODUCT",
    "SJZQ_SEQ_PRODUCT_IMAGE",
]

INDEXES = [
    "CREATE INDEX IDX_SJZQ_DEVICE_STATUS ON SJZQ_DEVICE(STATUS)",
    "CREATE INDEX IDX_SJZQ_DEVICE_PLATFORM ON SJZQ_DEVICE(PLATFORM_CODE)",
    "CREATE INDEX IDX_SJZQ_TASK_STATUS ON SJZQ_TASK(STATUS, PRIORITY)",
    "CREATE INDEX IDX_SJZQ_TASK_PLATFORM ON SJZQ_TASK(PLATFORM_CODE)",
    "CREATE INDEX IDX_SJZQ_TASK_DEVICE ON SJZQ_TASK(DEVICE_ID)",
    "CREATE INDEX IDX_SJZQ_TASK_ITEM_TASK ON SJZQ_TASK_ITEM(TASK_ID, STATUS)",
    "CREATE INDEX IDX_SJZQ_TASK_LOG_TASK ON SJZQ_TASK_LOG(TASK_ID)",
    "CREATE INDEX IDX_SJZQ_PRODUCT_TASK ON SJZQ_PRODUCT(TASK_ID)",
    "CREATE INDEX IDX_SJZQ_PRODUCT_PLATFORM ON SJZQ_PRODUCT(PLATFORM_CODE, ITEM_ID)",
    "CREATE INDEX IDX_SJZQ_PRODUCT_KEYWORD ON SJZQ_PRODUCT(KEYWORD)",
    "CREATE INDEX IDX_SJZQ_PRODUCT_APPROVAL ON SJZQ_PRODUCT(APPROVAL_NO)",
    "CREATE INDEX IDX_SJZQ_IMG_PRODUCT ON SJZQ_PRODUCT_IMAGE(PRODUCT_ID)",
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
                "SJZQ_PRODUCT_IMAGE",
                "SJZQ_PRODUCT",
                "SJZQ_TASK_LOG",
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
