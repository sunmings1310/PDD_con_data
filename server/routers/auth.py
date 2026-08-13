"""登录 / 个人中心。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from server.auth_util import (
    create_token,
    get_current_user,
    hash_password,
    load_user,
    verify_password,
    write_op_log,
)
from server.db import get_conn, row_as_dict, rows_as_dicts
from server.schemas import ApiOk

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
def login(body: dict, request: Request):
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    if not username or not password:
        return ApiOk(ok=False, message="请输入账号密码")
    ip = request.client.host if request.client else None
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT u.USER_ID, u.USERNAME, u.PASSWORD_HASH, u.REAL_NAME, u.MOBILE,
                   u.ROLE_ID, u.STATUS, r.ROLE_CODE, r.ROLE_NAME
              FROM SJZQ_USER u
              JOIN SJZQ_ROLE r ON r.ROLE_ID = u.ROLE_ID
             WHERE u.USERNAME = :u
            """,
            {"u": username},
        )
        user = row_as_dict(cur)
        if not user or not verify_password(password, user["password_hash"]):
            write_op_log(
                cur, user_id=None, username=username, action="login_fail",
                module="auth", detail="账号或密码错误", ip=ip,
            )
            return ApiOk(ok=False, message="账号或密码错误")
        if user.get("status") != "enabled":
            return ApiOk(ok=False, message="账号已禁用")
        cur.execute(
            """
            UPDATE SJZQ_USER
               SET LAST_LOGIN_AT = SYSTIMESTAMP, LAST_LOGIN_IP = :login_ip, UPDATE_TIME = SYSTIMESTAMP
             WHERE USER_ID = :user_id
            """,
            {"login_ip": ip, "user_id": user["user_id"]},
        )
        write_op_log(
            cur, user_id=user["user_id"], username=username, action="login",
            module="auth", detail="登录成功", ip=ip,
        )
        token = create_token(user)
        user.pop("password_hash", None)
        from server.auth_util import get_user_perms

        perms = get_user_perms(cur, int(user["role_id"]))
        return ApiOk(
            data={
                "token": token,
                "user": {**user, "perms": perms},
            }
        )


@router.get("/me")
def me(user=Depends(get_current_user)):
    return ApiOk(data=user)


@router.post("/change-password")
def change_password(body: dict, request: Request, user=Depends(get_current_user)):
    old = body.get("old_password") or ""
    new = body.get("new_password") or ""
    if len(new) < 6:
        return ApiOk(ok=False, message="新密码至少 6 位")
    with get_conn() as conn:
        cur = conn.cursor()
        full = load_user(cur, int(user["user_id"]))
        if not full or not verify_password(old, full["password_hash"]):
            return ApiOk(ok=False, message="原密码不正确")
        cur.execute(
            """
            UPDATE SJZQ_USER SET PASSWORD_HASH = :ph, UPDATE_TIME = SYSTIMESTAMP
             WHERE USER_ID = :id
            """,
            {"ph": hash_password(new), "id": user["user_id"]},
        )
        write_op_log(
            cur,
            user_id=user["user_id"],
            username=user["username"],
            action="change_password",
            module="auth",
            detail="修改密码",
            ip=request.client.host if request.client else None,
        )
        return ApiOk(message="密码已修改")


@router.get("/my-logs")
def my_logs(user=Depends(get_current_user), limit: int = 50):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT LOG_ID, ACTION_CODE, MODULE_CODE, DETAIL_TEXT, IP_ADDR, CREATE_TIME
              FROM SJZQ_OP_LOG
             WHERE USER_ID = :user_id
             ORDER BY LOG_ID DESC
             FETCH FIRST :lim ROWS ONLY
            """,
            {"user_id": user["user_id"], "lim": limit},
        )
        return ApiOk(data=rows_as_dicts(cur))
