"""登录鉴权工具。"""

from __future__ import annotations

import hashlib
import time
from typing import Any, Optional

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from server.config import settings
from server.db import get_conn, row_as_dict, rows_as_dicts

security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    salt = "sjzq_v1"
    return hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    return hash_password(password) == password_hash


def create_token(user: dict[str, Any]) -> str:
    payload = {
        "uid": user["user_id"],
        "username": user["username"],
        "role_code": user.get("role_code"),
        "exp": int(time.time()) + settings.jwt_expire_sec,
    }
    return jwt.encode(
        payload,
        settings.jwt_secret.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录") from e


def get_user_perms(cur, role_id: int) -> list[str]:
    cur.execute(
        "SELECT PERM_CODE FROM SJZQ_ROLE_PERM WHERE ROLE_ID = :r",
        {"r": role_id},
    )
    return [r[0] for r in cur.fetchall()]


def load_user(cur, user_id: int) -> Optional[dict[str, Any]]:
    cur.execute(
        """
        SELECT u.USER_ID, u.USERNAME, u.PASSWORD_HASH, u.REAL_NAME, u.MOBILE,
               u.ROLE_ID, u.STATUS, u.LAST_LOGIN_AT, u.LAST_LOGIN_IP, u.CREATE_TIME,
               r.ROLE_CODE, r.ROLE_NAME
          FROM SJZQ_USER u
          JOIN SJZQ_ROLE r ON r.ROLE_ID = u.ROLE_ID
         WHERE u.USER_ID = :id
        """,
        {"id": user_id},
    )
    return row_as_dict(cur)


def write_op_log(
    cur,
    *,
    user_id: Optional[int],
    username: Optional[str],
    action: str,
    module: str,
    detail: str = "",
    ip: Optional[str] = None,
) -> None:
    cur.execute("SELECT SJZQ_SEQ_OP_LOG.NEXTVAL FROM DUAL")
    log_id = int(cur.fetchone()[0])
    cur.execute(
        """
        INSERT INTO SJZQ_OP_LOG
        (LOG_ID, USER_ID, USERNAME, ACTION_CODE, MODULE_CODE, DETAIL_TEXT, IP_ADDR)
        VALUES (:log_id, :user_id, :username, :action_code, :module_code, :detail_text, :ip_addr)
        """,
        {
            "log_id": log_id,
            "user_id": user_id,
            "username": username,
            "action_code": action[:64],
            "module_code": (module or "")[:64],
            "detail_text": (detail or "")[:2000],
            "ip_addr": ip,
        },
    )


async def get_current_user(
    request: Request,
    cred: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict[str, Any]:
    if cred is None or not cred.credentials:
        raise HTTPException(status_code=401, detail="未登录")
    payload = decode_token(cred.credentials)
    with get_conn() as conn:
        cur = conn.cursor()
        user = load_user(cur, int(payload["uid"]))
        if not user or user.get("status") != "enabled":
            raise HTTPException(status_code=401, detail="账号不可用")
        perms = get_user_perms(cur, int(user["role_id"]))
    user.pop("password_hash", None)
    user["perms"] = perms
    request.state.user = user
    return user


def require_perms(*need: str):
    async def _dep(user: dict = Depends(get_current_user)) -> dict:
        perms = set(user.get("perms") or [])
        if user.get("role_code") == "super_admin":
            return user
        if not all(p in perms for p in need):
            raise HTTPException(status_code=403, detail="无权限")
        return user

    return _dep
