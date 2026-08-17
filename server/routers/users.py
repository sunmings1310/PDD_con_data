"""人员 / 角色 / 操作日志。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from server.auth_util import get_current_user, hash_password, require_perms, write_op_log
from server.tenant import require_tenant_perms
from server.db import get_conn, next_id, rows_as_dicts
from server.schemas import ApiOk

router = APIRouter(prefix="/api", tags=["rbac"])

PERM_CATALOG = [
    {"code": "device:view", "name": "设备查看"},
    {"code": "device:manage", "name": "设备管控"},
    {"code": "device:cast", "name": "实时投屏"},
    {"code": "task:view", "name": "任务查看"},
    {"code": "task:create", "name": "任务新增"},
    {"code": "task:dispatch", "name": "下发任务"},
    {"code": "task:delete", "name": "任务删除"},
    {"code": "task:review", "name": "任务审核"},
    {"code": "data:view", "name": "数据查看"},
    {"code": "data:export", "name": "数据导出"},
    {"code": "data:delete", "name": "数据删除"},
    {"code": "excel:import", "name": "Excel导入"},
    {"code": "excel:export", "name": "Excel导出"},
    {"code": "excel:match", "name": "Excel匹配"},
    {"code": "account:view", "name": "平台账号查看"},
    {"code": "account:manage", "name": "平台账号管理"},
    {"code": "report:view", "name": "经营报表查看"},
    {"code": "log:view", "name": "日志查看"},
    {"code": "user:manage", "name": "人员管理"},
    {"code": "role:manage", "name": "角色管理"},
    {"code": "system:config", "name": "系统配置"},
]


@router.get("/perms/catalog")
def perm_catalog(user=Depends(get_current_user)):
    return ApiOk(data=PERM_CATALOG)


@router.get("/users")
def list_users(
    username: str | None = None,
    role_id: int | None = None,
    status: str | None = None,
    tenant=Depends(require_tenant_perms("user:manage")),
):
    with get_conn() as conn:
        cur = conn.cursor()
        sql = """
            SELECT u.USER_ID, u.USERNAME, u.REAL_NAME, u.MOBILE, u.ROLE_ID, u.STATUS,
                   u.LAST_LOGIN_AT, u.CREATE_TIME, r.ROLE_NAME, r.ROLE_CODE
              FROM SJZQ_USER u
              JOIN SJZQ_ENTERPRISE_MEMBERSHIP m ON m.USER_ID=u.USER_ID
              JOIN SJZQ_ROLE r ON r.ROLE_ID = m.ROLE_ID
             WHERE m.ENTERPRISE_ID=:enterprise_id
        """
        params: dict = {"enterprise_id":tenant.enterprise_id}
        if username:
            sql += " AND u.USERNAME LIKE :un"
            params["un"] = f"%{username}%"
        if role_id is not None:
            sql += " AND u.ROLE_ID = :rid"
            params["rid"] = role_id
        if status:
            sql += " AND u.STATUS = :st"
            params["st"] = status
        sql += " ORDER BY u.USER_ID DESC"
        cur.execute(sql, params)
        return ApiOk(data=rows_as_dicts(cur))


@router.post("/users")
def create_user(body: dict, request: Request, user=Depends(get_current_user), tenant=Depends(require_tenant_perms("user:manage"))):
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    if not username:
        return ApiOk(ok=False, message="账号不能为空")
    if len(password) < 12:
        return ApiOk(ok=False, message="初始密码必须由管理员指定且至少 12 个字符")
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM SJZQ_USER WHERE USERNAME=:u", {"u": username})
        if int(cur.fetchone()[0]) > 0:
            return ApiOk(ok=False, message="账号已存在")
        uid = next_id(cur, "SJZQ_SEQ_USER")
        cur.execute(
            """
            INSERT INTO SJZQ_USER
            (USER_ID, USERNAME, PASSWORD_HASH, REAL_NAME, MOBILE, ROLE_ID, STATUS)
            VALUES (:id, :un, :ph, :rn, :mb, :rid, :st)
            """,
            {
                "id": uid,
                "un": username,
                "ph": hash_password(password),
                "rn": body.get("real_name"),
                "mb": body.get("mobile"),
                "rid": body.get("role_id"),
                "st": body.get("status") or "enabled",
            },
        )
        membership_id = next_id(cur, "SJZQ_SEQ_ENT_MEMBERSHIP")
        cur.execute("""INSERT INTO SJZQ_ENTERPRISE_MEMBERSHIP
            (MEMBERSHIP_ID,ENTERPRISE_ID,USER_ID,ROLE_ID,STATUS)
            VALUES (:mid,:enterprise_id,:uid,:role_id,'active')""",
            {"mid":membership_id,"enterprise_id":tenant.enterprise_id,"uid":uid,"role_id":body.get("role_id")})
        write_op_log(
            cur, user_id=user["user_id"], username=user["username"],
            action="user_create", module="user", detail=f"新增用户 {username}",
            ip=request.client.host if request.client else None,
        )
        return ApiOk(data={"user_id": uid})


@router.put("/users/{user_id}")
def update_user(user_id: int, body: dict, request: Request, user=Depends(get_current_user), tenant=Depends(require_tenant_perms("user:manage"))):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE SJZQ_USER SET REAL_NAME=:rn,MOBILE=:mb,UPDATE_TIME=SYSTIMESTAMP
             WHERE USER_ID=:id AND EXISTS (SELECT 1 FROM SJZQ_ENTERPRISE_MEMBERSHIP m
                 WHERE m.USER_ID=SJZQ_USER.USER_ID AND m.ENTERPRISE_ID=:enterprise_id)
            """,
            {
                "rn": body.get("real_name"),
                "mb": body.get("mobile"),
                "id": user_id,
                "enterprise_id":tenant.enterprise_id,
            },
        )
        cur.execute("""UPDATE SJZQ_ENTERPRISE_MEMBERSHIP SET ROLE_ID=:rid,STATUS=:st,UPDATE_TIME=SYSTIMESTAMP
                        WHERE ENTERPRISE_ID=:enterprise_id AND USER_ID=:id""",
                    {"rid":body.get("role_id"),"st":body.get("status") or "active",
                     "enterprise_id":tenant.enterprise_id,"id":user_id})
        write_op_log(
            cur, user_id=user["user_id"], username=user["username"],
            action="user_update", module="user", detail=f"编辑用户 {user_id}",
            ip=request.client.host if request.client else None,
        )
        return ApiOk()


@router.post("/users/{user_id}/reset-password")
def reset_password(user_id: int, body: dict, request: Request, user=Depends(get_current_user), tenant=Depends(require_tenant_perms("user:manage"))):
    pwd = body.get("password") or ""
    if len(pwd) < 12:
        return ApiOk(ok=False, message="临时密码必须由管理员指定且至少 12 个字符")
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """UPDATE SJZQ_USER SET PASSWORD_HASH=:ph,UPDATE_TIME=SYSTIMESTAMP WHERE USER_ID=:id
                AND EXISTS (SELECT 1 FROM SJZQ_ENTERPRISE_MEMBERSHIP m WHERE m.USER_ID=SJZQ_USER.USER_ID
                             AND m.ENTERPRISE_ID=:enterprise_id)""",
            {"ph": hash_password(pwd), "id": user_id,"enterprise_id":tenant.enterprise_id},
        )
        write_op_log(
            cur, user_id=user["user_id"], username=user["username"],
            action="user_reset_pwd", module="user", detail=f"重置密码 user={user_id}",
            ip=request.client.host if request.client else None,
        )
        return ApiOk(message="已重置密码")


@router.delete("/users/{user_id}")
def delete_user(user_id: int, request: Request, user=Depends(get_current_user), tenant=Depends(require_tenant_perms("user:manage"))):
    if int(user_id) == int(user["user_id"]):
        return ApiOk(ok=False, message="不能删除自己")
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM SJZQ_ENTERPRISE_MEMBERSHIP WHERE ENTERPRISE_ID=:enterprise_id AND USER_ID=:id",
                    {"enterprise_id":tenant.enterprise_id,"id":user_id})
        write_op_log(
            cur, user_id=user["user_id"], username=user["username"],
            action="user_delete", module="user", detail=f"删除用户 {user_id}",
            ip=request.client.host if request.client else None,
        )
        return ApiOk()


@router.get("/roles")
def list_roles(_=Depends(get_current_user)):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT ROLE_ID, ROLE_CODE, ROLE_NAME, REMARK, IS_SYSTEM, CREATE_TIME
              FROM SJZQ_ROLE ORDER BY ROLE_ID
            """
        )
        roles = rows_as_dicts(cur)
        for r in roles:
            cur.execute(
                "SELECT PERM_CODE FROM SJZQ_ROLE_PERM WHERE ROLE_ID=:id",
                {"id": r["role_id"]},
            )
            r["perms"] = [x[0] for x in cur.fetchall()]
        return ApiOk(data=roles)


@router.post("/roles")
def create_role(body: dict, request: Request, user=Depends(require_perms("role:manage"))):
    code = (body.get("role_code") or "").strip()
    name = (body.get("role_name") or "").strip()
    if not code or not name:
        return ApiOk(ok=False, message="角色编码/名称不能为空")
    with get_conn() as conn:
        cur = conn.cursor()
        rid = next_id(cur, "SJZQ_SEQ_ROLE")
        cur.execute(
            """
            INSERT INTO SJZQ_ROLE (ROLE_ID, ROLE_CODE, ROLE_NAME, REMARK, IS_SYSTEM)
            VALUES (:id, :c, :n, :r, 0)
            """,
            {"id": rid, "c": code, "n": name, "r": body.get("remark")},
        )
        for p in body.get("perms") or []:
            cur.execute(
                "INSERT INTO SJZQ_ROLE_PERM (ROLE_ID, PERM_CODE) VALUES (:r, :p)",
                {"r": rid, "p": p},
            )
        write_op_log(
            cur, user_id=user["user_id"], username=user["username"],
            action="role_create", module="role", detail=f"新建角色 {code}",
            ip=request.client.host if request.client else None,
        )
        return ApiOk(data={"role_id": rid})


@router.put("/roles/{role_id}")
def update_role(role_id: int, body: dict, request: Request, user=Depends(require_perms("role:manage"))):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE SJZQ_ROLE SET ROLE_NAME=:n, REMARK=:r WHERE ROLE_ID=:id",
            {"n": body.get("role_name"), "r": body.get("remark"), "id": role_id},
        )
        cur.execute("DELETE FROM SJZQ_ROLE_PERM WHERE ROLE_ID=:id", {"id": role_id})
        for p in body.get("perms") or []:
            cur.execute(
                "INSERT INTO SJZQ_ROLE_PERM (ROLE_ID, PERM_CODE) VALUES (:r, :p)",
                {"r": role_id, "p": p},
            )
        write_op_log(
            cur, user_id=user["user_id"], username=user["username"],
            action="role_update", module="role", detail=f"更新角色 {role_id}",
            ip=request.client.host if request.client else None,
        )
        return ApiOk()


@router.get("/op-logs")
def list_op_logs(
    username: str | None = None,
    action: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    tenant=Depends(require_tenant_perms("log:view")),
):
    with get_conn() as conn:
        cur = conn.cursor()
        sql = """
            SELECT LOG_ID, USER_ID, USERNAME, ACTION_CODE, MODULE_CODE,
                   DETAIL_TEXT, IP_ADDR, CREATE_TIME
              FROM SJZQ_OP_LOG WHERE ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id
        """
        params: dict = dict(tenant.binds)
        if username:
            sql += " AND USERNAME LIKE :un"
            params["un"] = f"%{username}%"
        if action:
            sql += " AND ACTION_CODE = :ac"
            params["ac"] = action
        sql += " ORDER BY LOG_ID DESC FETCH FIRST :lim ROWS ONLY"
        params["lim"] = limit
        cur.execute(sql, params)
        return ApiOk(data=rows_as_dicts(cur))
