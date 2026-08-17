"""平台账号养护、设备绑定、封禁与异常告警。"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request

from server.auth_util import require_perms, write_op_log
from server.db import get_conn, next_id, row_as_dict, rows_as_dicts
from server.schemas import ApiOk
from server.tenant import require_tenant_perms

router = APIRouter(prefix="/api/accounts", tags=["accounts"])
BAD_STATUSES = {"blocked", "abnormal"}
VALID_STATUSES = {"nurturing", "ready", "blocked", "abnormal", "disabled"}


def _refresh_mature(cur, tenant) -> None:
    cur.execute(
        """
        UPDATE SJZQ_PLATFORM_ACCOUNT
           SET STATUS='ready', UPDATE_TIME=SYSTIMESTAMP
         WHERE STATUS='nurturing' AND MATURE_AT IS NOT NULL AND MATURE_AT <= TRUNC(SYSDATE)
           AND ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id
        """
        , tenant.binds
    )


def _check_owner_alert(cur, owner_user_id: int, tenant) -> None:
    cur.execute(
        """
        SELECT COUNT(*),
               SUM(CASE WHEN STATUS IN ('blocked','abnormal') THEN 1 ELSE 0 END)
          FROM SJZQ_PLATFORM_ACCOUNT
         WHERE OWNER_USER_ID=:owner_id AND STATUS <> 'disabled'
           AND ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id
        """,
        {"owner_id": owner_user_id, **tenant.binds},
    )
    total, bad = cur.fetchone()
    total, bad = int(total or 0), int(bad or 0)
    if total == 0 or bad != total:
        return
    cur.execute(
        """
        SELECT COUNT(*) FROM SJZQ_ALERT
         WHERE ALERT_TYPE='all_accounts_abnormal' AND OWNER_USER_ID=:owner_id AND STATUS='unread'
           AND ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id
        """,
        {"owner_id": owner_user_id, **tenant.binds},
    )
    if int(cur.fetchone()[0] or 0) > 0:
        return
    alert_id = next_id(cur, "SJZQ_SEQ_ALERT")
    cur.execute(
        """
        INSERT INTO SJZQ_ALERT (ALERT_ID, ALERT_TYPE, OWNER_USER_ID, LEVEL_CODE, MESSAGE,ENTERPRISE_ID,WORKSPACE_ID)
        VALUES (:id, 'all_accounts_abnormal', :owner_id, 'critical', :message,:enterprise_id,:workspace_id)
        """,
        {"id": alert_id, "owner_id": owner_user_id, "message": f"运营用户 #{owner_user_id} 负责的全部平台账号均已异常或封禁", **tenant.binds},
    )


@router.get("")
def list_accounts(user=Depends(require_perms("account:view")), tenant=Depends(require_tenant_perms("account:view"))):
    with get_conn() as conn:
        cur = conn.cursor()
        _refresh_mature(cur, tenant)
        sql = """
            SELECT a.ACCOUNT_ID, a.PLATFORM_CODE, a.ACCOUNT_NAME, a.MOBILE,
                   a.OWNER_USER_ID, u.USERNAME OWNER_USERNAME, u.REAL_NAME OWNER_REAL_NAME,
                   a.DEVICE_ID, d.DEVICE_NAME, a.STATUS, a.NURTURE_START,
                   a.NURTURE_DAYS, a.MATURE_AT, a.LAST_CHECK_AT,
                   a.BLOCK_REASON, a.REMARK, a.CREATE_TIME, a.UPDATE_TIME
              FROM SJZQ_PLATFORM_ACCOUNT a
              JOIN SJZQ_USER u ON u.USER_ID=a.OWNER_USER_ID
              LEFT JOIN SJZQ_DEVICE d ON d.DEVICE_ID=a.DEVICE_ID
        """
        sql += " WHERE a.ENTERPRISE_ID=:enterprise_id AND a.WORKSPACE_ID=:workspace_id"
        params = dict(tenant.binds)
        if tenant.role_code != "super_admin":
            sql += " AND a.OWNER_USER_ID=:owner_id"
            params["owner_id"] = int(user["user_id"])
        sql += " ORDER BY a.STATUS, a.MATURE_AT, a.ACCOUNT_ID DESC"
        cur.execute(sql, params)
        return ApiOk(data=rows_as_dicts(cur))


@router.get("/operators")
def list_account_operators(user=Depends(require_perms("account:view")), tenant=Depends(require_tenant_perms("account:view"))):
    with get_conn() as conn:
        cur = conn.cursor()
        if tenant.role_code == "super_admin":
            cur.execute(
                """
                SELECT u.USER_ID, u.USERNAME, u.REAL_NAME
                  FROM SJZQ_USER u JOIN SJZQ_ENTERPRISE_MEMBERSHIP m ON m.USER_ID=u.USER_ID
                  JOIN SJZQ_ROLE r ON r.ROLE_ID=m.ROLE_ID
                 WHERE u.STATUS='enabled' AND m.STATUS='active' AND m.ENTERPRISE_ID=:enterprise_id
                   AND r.ROLE_CODE IN ('operator','super_admin')
                 ORDER BY u.USER_ID
                """, {"enterprise_id": tenant.enterprise_id}
            )
            return ApiOk(data=rows_as_dicts(cur))
        return ApiOk(data=[{"user_id": user["user_id"], "username": user["username"], "real_name": user.get("real_name")}])


def _validated_owner(body: dict, user: dict, tenant) -> int:
    owner = int(body.get("owner_user_id") or user["user_id"])
    if tenant.role_code != "super_admin" and owner != int(user["user_id"]):
        raise ValueError("运营只能维护本人账号")
    return owner


def _validate_device(cur, owner: int, device_id: int | None, tenant) -> None:
    if not device_id:
        return
    cur.execute("""SELECT OWNER_USER_ID FROM SJZQ_DEVICE WHERE DEVICE_ID=:id
                    AND ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id
                    AND REVOKED_AT IS NULL""", {"id": device_id, **tenant.binds})
    row = cur.fetchone()
    if not row:
        raise ValueError("设备不存在")
    if row[0] is not None and int(row[0]) != owner:
        raise ValueError("账号只能绑定同一运营名下设备")


@router.post("")
def create_account(body: dict, request: Request, user=Depends(require_perms("account:manage")),
                   tenant=Depends(require_tenant_perms("account:manage"))):
    try:
        owner = _validated_owner(body, user, tenant)
        days = int(body.get("nurture_days") or 5)
        if days not in (5, 6, 7):
            raise ValueError("养护天数只能为5、6或7天")
        platform = str(body.get("platform_code") or "pinduoduo").strip()
        if platform not in {"pinduoduo", "tmall"}:
            raise ValueError("账号平台仅支持拼多多或天猫")
        name = str(body.get("account_name") or "").strip()
        if not name:
            raise ValueError("账号名称不能为空")
        device_id = int(body["device_id"]) if body.get("device_id") else None
        start = date.fromisoformat(body.get("nurture_start")) if body.get("nurture_start") else date.today()
    except (ValueError, TypeError) as exc:
        return ApiOk(ok=False, message=str(exc))
    with get_conn() as conn:
        cur = conn.cursor()
        try:
            _validate_device(cur, owner, device_id, tenant)
        except ValueError as exc:
            return ApiOk(ok=False, message=str(exc))
        account_id = next_id(cur, "SJZQ_SEQ_PLATFORM_ACCOUNT")
        cur.execute(
            """
            INSERT INTO SJZQ_PLATFORM_ACCOUNT (
                ACCOUNT_ID, PLATFORM_CODE, ACCOUNT_NAME, MOBILE, OWNER_USER_ID, DEVICE_ID,
                STATUS, NURTURE_START, NURTURE_DAYS, MATURE_AT, REMARK,ENTERPRISE_ID,WORKSPACE_ID
            ) VALUES (
                :id, :platform, :name, :mobile, :owner, :device_id,
                'nurturing', :start_date, :days, :mature_at, :remark,:enterprise_id,:workspace_id
            )
            """,
            {
                "id": account_id, "platform": platform, "name": name,
                "mobile": body.get("mobile"), "owner": owner, "device_id": device_id,
                "start_date": start, "days": days, "mature_at": start + timedelta(days=days),
                "remark": body.get("remark"), **tenant.binds,
            },
        )
        write_op_log(cur, user_id=user["user_id"], username=user["username"], action="account_create", module="account", detail=f"新增{platform}账号 {name}", ip=request.client.host if request.client else None, **tenant.binds)
        return ApiOk(data={"account_id": account_id})


@router.put("/{account_id}")
def update_account(account_id: int, body: dict, request: Request, user=Depends(require_perms("account:manage")),
                   tenant=Depends(require_tenant_perms("account:manage"))):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT * FROM SJZQ_PLATFORM_ACCOUNT WHERE ACCOUNT_ID=:id
                        AND ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id""",
                    {"id": account_id, **tenant.binds})
        old = row_as_dict(cur)
        if not old:
            return ApiOk(ok=False, message="账号不存在")
        if tenant.role_code != "super_admin" and int(old["owner_user_id"]) != int(user["user_id"]):
            return ApiOk(ok=False, message="运营只能维护本人账号")
        try:
            owner = int(body.get("owner_user_id") or old["owner_user_id"])
            if tenant.role_code != "super_admin" and owner != int(user["user_id"]):
                raise ValueError("运营只能维护本人账号")
            status = str(body.get("status") or old["status"]).lower()
            if status not in VALID_STATUSES:
                raise ValueError("无效账号状态")
            days = int(body.get("nurture_days") or old["nurture_days"] or 5)
            if days not in (5, 6, 7):
                raise ValueError("养护天数只能为5、6或7天")
            device_id = int(body["device_id"]) if body.get("device_id") else None
            _validate_device(cur, owner, device_id, tenant)
        except (ValueError, TypeError) as exc:
            return ApiOk(ok=False, message=str(exc))
        cur.execute(
            """
            UPDATE SJZQ_PLATFORM_ACCOUNT
               SET OWNER_USER_ID=:owner, DEVICE_ID=:device_id, STATUS=:status,
                   NURTURE_DAYS=:days, MATURE_AT=NURTURE_START+:days,
                   LAST_CHECK_AT=SYSTIMESTAMP, BLOCK_REASON=:reason, REMARK=:remark,
                   UPDATE_TIME=SYSTIMESTAMP
             WHERE ACCOUNT_ID=:id AND ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id
            """,
            {"owner": owner, "device_id": device_id, "status": status, "days": days,
             "reason": body.get("block_reason"), "remark": body.get("remark"), "id": account_id, **tenant.binds},
        )
        _check_owner_alert(cur, owner, tenant)
        write_op_log(cur, user_id=user["user_id"], username=user["username"], action="account_update", module="account", detail=f"更新账号 #{account_id} 状态={status}", ip=request.client.host if request.client else None, **tenant.binds)
        return ApiOk()


@router.get("/alerts")
def list_alerts(user=Depends(require_perms("account:view")), tenant=Depends(require_tenant_perms("account:view"))):
    with get_conn() as conn:
        cur = conn.cursor()
        sql = """SELECT ALERT_ID, ALERT_TYPE, OWNER_USER_ID, LEVEL_CODE, MESSAGE, STATUS, CREATE_TIME, ACK_TIME
                   FROM SJZQ_ALERT WHERE ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id"""
        params = dict(tenant.binds)
        if tenant.role_code != "super_admin":
            sql += " AND OWNER_USER_ID=:owner_id"
            params["owner_id"] = int(user["user_id"])
        sql += " ORDER BY ALERT_ID DESC FETCH FIRST 100 ROWS ONLY"
        cur.execute(sql, params)
        return ApiOk(data=rows_as_dicts(cur))


@router.post("/alerts/{alert_id}/ack")
def ack_alert(alert_id: int, user=Depends(require_perms("account:manage")),
              tenant=Depends(require_tenant_perms("account:manage"))):
    with get_conn() as conn:
        cur = conn.cursor()
        sql = """UPDATE SJZQ_ALERT SET STATUS='acked', ACK_TIME=SYSTIMESTAMP, ACK_USER_ID=:ack_user_id
                  WHERE ALERT_ID=:id AND ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id"""
        params = {"ack_user_id": user["user_id"], "id": alert_id, **tenant.binds}
        if tenant.role_code != "super_admin":
            sql += " AND OWNER_USER_ID=:owner_id"
            params["owner_id"] = user["user_id"]
        cur.execute(sql, params)
        return ApiOk(ok=cur.rowcount > 0, message="已确认" if cur.rowcount > 0 else "告警不存在")
