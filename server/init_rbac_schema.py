"""扩展 SJZQ_ 用户 / 角色 / 权限 / 操作日志表，并按外部配置初始化管理员。"""

from __future__ import annotations

import hashlib
import os
import sys

import oracledb

from server.config import settings


DDL = [
    """
    CREATE TABLE SJZQ_ROLE (
        ROLE_ID       NUMBER(18)    NOT NULL,
        ROLE_CODE     VARCHAR2(64)  NOT NULL,
        ROLE_NAME     VARCHAR2(128) NOT NULL,
        REMARK        VARCHAR2(256),
        IS_SYSTEM     NUMBER(1)     DEFAULT 0 NOT NULL,
        CREATE_TIME   TIMESTAMP     DEFAULT SYSTIMESTAMP NOT NULL,
        CONSTRAINT PK_SJZQ_ROLE PRIMARY KEY (ROLE_ID),
        CONSTRAINT UK_SJZQ_ROLE_CODE UNIQUE (ROLE_CODE)
    )
    """,
    """
    CREATE TABLE SJZQ_ROLE_PERM (
        ROLE_ID       NUMBER(18)    NOT NULL,
        PERM_CODE     VARCHAR2(64)  NOT NULL,
        CONSTRAINT PK_SJZQ_ROLE_PERM PRIMARY KEY (ROLE_ID, PERM_CODE)
    )
    """,
    """
    CREATE TABLE SJZQ_USER (
        USER_ID       NUMBER(18)    NOT NULL,
        USERNAME      VARCHAR2(64)  NOT NULL,
        PASSWORD_HASH VARCHAR2(128) NOT NULL,
        REAL_NAME     VARCHAR2(64),
        MOBILE        VARCHAR2(32),
        ROLE_ID       NUMBER(18)    NOT NULL,
        STATUS        VARCHAR2(16)  DEFAULT 'enabled' NOT NULL,
        LAST_LOGIN_AT TIMESTAMP,
        LAST_LOGIN_IP VARCHAR2(64),
        CREATE_TIME   TIMESTAMP     DEFAULT SYSTIMESTAMP NOT NULL,
        UPDATE_TIME   TIMESTAMP     DEFAULT SYSTIMESTAMP NOT NULL,
        CONSTRAINT PK_SJZQ_USER PRIMARY KEY (USER_ID),
        CONSTRAINT UK_SJZQ_USER_NAME UNIQUE (USERNAME)
    )
    """,
    """
    CREATE TABLE SJZQ_OP_LOG (
        LOG_ID        NUMBER(18)    NOT NULL,
        USER_ID       NUMBER(18),
        USERNAME      VARCHAR2(64),
        ACTION_CODE   VARCHAR2(64)  NOT NULL,
        MODULE_CODE   VARCHAR2(64),
        DETAIL_TEXT   VARCHAR2(2000),
        IP_ADDR       VARCHAR2(64),
        CREATE_TIME   TIMESTAMP     DEFAULT SYSTIMESTAMP NOT NULL,
        CONSTRAINT PK_SJZQ_OP_LOG PRIMARY KEY (LOG_ID)
    )
    """,
    """
    CREATE TABLE SJZQ_SYS_CONFIG (
        CONFIG_KEY    VARCHAR2(128) NOT NULL,
        CONFIG_VALUE  CLOB,
        REMARK        VARCHAR2(256),
        UPDATE_TIME   TIMESTAMP     DEFAULT SYSTIMESTAMP NOT NULL,
        CONSTRAINT PK_SJZQ_SYS_CONFIG PRIMARY KEY (CONFIG_KEY)
    )
    """,
]

SEQS = ["SJZQ_SEQ_ROLE", "SJZQ_SEQ_USER", "SJZQ_SEQ_OP_LOG"]

# 权限码
ALL_PERMS = [
    "device:view", "device:manage", "device:cast",
    "task:view", "task:create", "task:dispatch", "task:delete", "task:review",
    "data:view", "data:export", "data:delete",
    "excel:import", "excel:export", "excel:match",
    "log:view", "account:view", "account:manage", "report:view",
    "user:manage", "role:manage", "system:config",
]

ROLE_DEFS = [
    ("super_admin", "超级管理员", 1, ALL_PERMS),
    (
        "operator",
        "业务操作员",
        1,
        [
            "device:view", "device:manage", "device:cast",
            "task:view", "task:create", "task:dispatch", "task:review",
            "data:view", "data:export",
            "excel:import", "excel:export", "excel:match",
            "log:view", "account:view", "account:manage", "report:view",
        ],
    ),
    (
        "viewer",
        "只读查看员",
        1,
        ["device:view", "task:view", "data:view", "log:view", "account:view", "report:view"],
    ),
]


def _hash_password(password: str) -> str:
    # 简单可移植哈希：sha256 + salt 前缀（后续可换 bcrypt）
    salt = "sjzq_v1"
    return hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()


def _bootstrap_admin_credentials() -> tuple[str, str]:
    username = os.getenv("INITIAL_ADMIN_USERNAME", "").strip()
    password = os.getenv("INITIAL_ADMIN_PASSWORD", "")
    missing = [
        name
        for name, value in (
            ("INITIAL_ADMIN_USERNAME", username),
            ("INITIAL_ADMIN_PASSWORD", password),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(
            "Initial administrator configuration is missing: " + ", ".join(missing)
        )
    if len(password) < 12:
        raise RuntimeError("INITIAL_ADMIN_PASSWORD must contain at least 12 characters")
    return username, password


def _exists_table(cur, name: str) -> bool:
    cur.execute("SELECT COUNT(*) FROM user_tables WHERE table_name = :n", {"n": name})
    return int(cur.fetchone()[0]) > 0


def _exists_seq(cur, name: str) -> bool:
    cur.execute("SELECT COUNT(*) FROM user_sequences WHERE sequence_name = :n", {"n": name})
    return int(cur.fetchone()[0]) > 0


def init_rbac() -> None:
    conn = oracledb.connect(
        user=settings.oracle_user,
        password=settings.oracle_password.get_secret_value(),
        dsn=settings.oracle_dsn,
    )
    cur = conn.cursor()
    try:
        for ddl in DDL:
            t = ddl.split("CREATE TABLE")[1].split("(")[0].strip()
            if _exists_table(cur, t):
                print("SKIP", t)
            else:
                cur.execute(ddl)
                print("CREATE", t)

        for s in SEQS:
            if _exists_seq(cur, s):
                print("SKIP", s)
            else:
                cur.execute(f"CREATE SEQUENCE {s} START WITH 1 INCREMENT BY 1 NOCACHE")
                print("CREATE", s)

        role_ids: dict[str, int] = {}
        for code, name, is_sys, perms in ROLE_DEFS:
            cur.execute("SELECT ROLE_ID FROM SJZQ_ROLE WHERE ROLE_CODE = :c", {"c": code})
            row = cur.fetchone()
            if row:
                rid = int(row[0])
                print("SKIP ROLE", code)
            else:
                cur.execute("SELECT SJZQ_SEQ_ROLE.NEXTVAL FROM DUAL")
                rid = int(cur.fetchone()[0])
                cur.execute(
                    """
                    INSERT INTO SJZQ_ROLE (ROLE_ID, ROLE_CODE, ROLE_NAME, REMARK, IS_SYSTEM)
                    VALUES (:id, :c, :n, :r, :s)
                    """,
                    {"id": rid, "c": code, "n": name, "r": "系统预置", "s": is_sys},
                )
                print("SEED ROLE", code)
            role_ids[code] = rid
            for p in perms:
                cur.execute(
                    "SELECT COUNT(*) FROM SJZQ_ROLE_PERM WHERE ROLE_ID=:r AND PERM_CODE=:p",
                    {"r": rid, "p": p},
                )
                if int(cur.fetchone()[0]) == 0:
                    cur.execute(
                        "INSERT INTO SJZQ_ROLE_PERM (ROLE_ID, PERM_CODE) VALUES (:r, :p)",
                        {"r": rid, "p": p},
                    )

        # 已有超级管理员时保持现状；全新部署必须从环境变量注入首个管理员。
        cur.execute(
            """
            SELECT COUNT(*)
              FROM SJZQ_USER u
              JOIN SJZQ_ROLE r ON r.ROLE_ID = u.ROLE_ID
             WHERE r.ROLE_CODE = 'super_admin'
            """
        )
        if int(cur.fetchone()[0]) == 0:
            admin_username, admin_password = _bootstrap_admin_credentials()
            cur.execute("SELECT SJZQ_SEQ_USER.NEXTVAL FROM DUAL")
            uid = int(cur.fetchone()[0])
            cur.execute(
                """
                INSERT INTO SJZQ_USER
                (USER_ID, USERNAME, PASSWORD_HASH, REAL_NAME, ROLE_ID, STATUS)
                VALUES (:id, :username, :ph, '超级管理员', :rid, 'enabled')
                """,
                {
                    "id": uid,
                    "username": admin_username,
                    "ph": _hash_password(admin_password),
                    "rid": role_ids["super_admin"],
                },
            )
            print("SEED INITIAL SUPER ADMIN")
        else:
            print("SKIP INITIAL SUPER ADMIN")

        # 扩展设备表字段（若缺失）
        cur.execute(
            """
            SELECT COUNT(*) FROM user_tab_columns
             WHERE table_name='SJZQ_DEVICE' AND column_name='OWNER_USER_ID'
            """
        )
        if int(cur.fetchone()[0]) == 0:
            cur.execute("ALTER TABLE SJZQ_DEVICE ADD (OWNER_USER_ID NUMBER(18), GROUP_NAME VARCHAR2(64))")
            print("ALTER SJZQ_DEVICE add owner/group")

        cur.execute(
            """
            SELECT COUNT(*) FROM user_tab_columns
             WHERE table_name='SJZQ_TASK' AND column_name='CREATE_USER_ID'
            """
        )
        if int(cur.fetchone()[0]) == 0:
            cur.execute(
                "ALTER TABLE SJZQ_TASK ADD (CREATE_USER_ID NUMBER(18), CREATE_USERNAME VARCHAR2(64))"
            )
            print("ALTER SJZQ_TASK add create user")

        conn.commit()
        print("RBAC OK")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    init_rbac()
