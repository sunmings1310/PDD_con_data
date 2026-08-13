"""平台账号养护、设备绑定、封禁与异常告警。"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request

from server.auth_util import require_perms, write_op_log
from server.db import get_conn, next_id, row_as_dict, rows_as_dicts
from server.schemas import ApiOk

router = APIRouter(prefix="/api/accounts", tags=["accounts"])
BAD_STATUSES = {"blocked", "abnormal"}
VALID_STATUSES = {"nurturing", "ready", "blocked", "abnormal", "disabled"}


def _is_admin(user: dict) -> bool:
    return user.get("role_code") == "super_admin"


def _refresh_mature(cur) -> None:
    cur.execute(
        """
        UPDATE SJZQ_PLATFORM_ACCOUNT
           SET STATUS='ready', UPDATE_TIME=SYSTIMESTAMP
         WHERE STATUS='nurturing' AND MATURE_AT IS NOT NULL AND MATURE_AT <= TRUNC(SYSDATE)
        """
    )


def _check_owner_alert(cur, owner_user_id: int) -> None:
    cur.execute(
        """
        SELECT COUNT(*),
               SUM(CASE WHEN STATUS IN ('blocked','abnormal') THEN 1 ELSE 0 END)
          FROM SJZQ_PLATFORM_ACCOUNT
         WHERE OWNER_USER_ID=:owner_id AND STATUS <> 'disabled'
        """,
        {"owner_id": owner_user_id},
    )
    total, bad = cur.fetchone()
    total, bad = int(total or 0), int(bad or 0)
    if total == 0 or bad != total:
        return
    cur.execute(
        """
        SELECT COUNT(*) FROM SJZQ_ALERT
         WHERE ALERT_TYPE='all_accounts_abnormal' AND OWNER_USER_ID=:owner_id AND STATUS='unread'
        """,
        {"owner_id": owner_user_id},
    )
    if int(cur.fetchone()[0] or 0) > 0:
        return
    alert_id = next_id(cur, "SJZQ_SEQ_ALERT")
    cur.execute(
        """
        INSERT INTO SJZQ_ALERT (ALERT_ID, ALERT_TYPE, OWNER_USER_ID, LEVEL_CODE, MESSAGE)
        VALUES (:id, 'all_accounts_abnormal', :owner_id, 'critical', :message)
        """,
        {"id": alert_id, "owner_id": owner_user_id, "message": f"运营用户 #{owner_user_id} 负责的全部平台账号均已异常或封禁"},
    )


@router.get("")
def list_accounts(user=Depends(require_perms("account:view"))):
    with get_conn() as conn:
        cur = conn.cursor()
        _refresh_mature(cur)
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
        params = {}
        if not _is_admin(user):
            sql += " WHERE a.OWNER_USER_ID=:owner_id"
            params["owner_id"] = int(user["user_id"])
        sql += " ORDER BY a.STATUS, a.MATURE_AT, a.ACCOUNT_ID DESC"
        cur.execute(sql, params)
        return ApiOk(data=rows_as_dicts(cur))


@router.get("/operators")
def list_account_operators(user=Depends(require_perms("account:view"))):
    with get_conn() as conn:
        cur = conn.cursor()
        if _is_admin(user):
            cur.execute(
                """
                SELECT u.USER_ID, u.USERNAME, u.REAL_NAME
                  FROM SJZQ_USER u JOIN SJZQ_ROLE r ON r.ROLE_ID=u.ROLE_ID
                 WHERE u.STATUS='enabled' AND r.ROLE_CODE IN ('operator','super_admin')
                 ORDER BY u.USER_ID
                """
            )
            return ApiOk(data=rows_as_dicts(cur))
        return ApiOk(data=[{"user_id": user["user_id"], "username": user["username"], "real_name": user.get("real_name")}])


def _validated_owner(body: dict, user: dict) -> int:
    owner = int(body.get("owner_user_id") or user["user_id"])
    if not _is_admin(user) and owner != int(user["user_id"]):
        raise ValueError("运营只能维护本人账号")
    return owner


def _validate_device(cur, owner: int, device_id: int | None) -> None:
    if not device_id:
        return
    cur.execute("SELECT OWNER_USER_ID FROM SJZQ_DEVICE WHERE DEVICE_ID=:id", {"id": device_id})
    row = cur.fetchone()
    if not row:
        raise ValueError("设备不存在")
    if row[0] is not None and int(row[0]) != owner:
        raise ValueError("账号只能绑定同一运营名下设备")


@router.post("")
def create_account(body: dict, request: Request, user=Depends(require_perms("account:manage"))):
    try:
        owner = _validated_owner(body, user)
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
            _validate_device(cur, owner, device_id)
        except ValueError as exc:
            return ApiOk(ok=False, message=str(exc))
        account_id = next_id(cur, "SJZQ_SEQ_PLATFORM_ACCOUNT")
        cur.execute(
            """
            INSERT INTO SJZQ_PLATFORM_ACCOUNT (
                ACCOUNT_ID, PLATFORM_CODE, ACCOUNT_NAME, MOBILE, OWNER_USER_ID, DEVICE_ID,
                STATUS, NURTURE_START, NURTURE_DAYS, MATURE_AT, REMARK
            ) VALUES (
                :id, :platform, :name, :mobile, :owner, :device_id,
                'nurturing', :start_date, :days, :mature_at, :remark
            )
            """,
            {
                "id": account_id, "platform": platform, "name": name,
                "mobile": body.get("mobile"), "owner": owner, "device_id": device_id,
                "start_date": start, "days": days, "mature_at": start + timedelta(days=days),
                "remark": body.get("remark"),
            },
        )
        write_op_log(cur, user_id=user["user_id"], username=user["username"], action="account_create", module="account", detail=f"新增{platform}账号 {name}", ip=request.client.host if request.client else None)
        return ApiOk(data={"account_id": account_id})


@router.put("/{account_id}")
def update_account(account_id: int, body: dict, request: Request, user=Depends(require_perms("account:manage"))):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM SJZQ_PLATFORM_ACCOUNT WHERE ACCOUNT_ID=:id", {"id": account_id})
        old = row_as_dict(cur)
        if not old:
            return ApiOk(ok=False, message="账号不存在")
        if not _is_admin(user) and int(old["owner_user_id"]) != int(user["user_id"]):
            return ApiOk(ok=False, message="运营只能维护本人账号")
        try:
            owner = int(body.get("owner_user_id") or old["owner_user_id"])
            if not _is_admin(user) and owner != int(user["user_id"]):
                raise ValueError("运营只能维护本人账号")
            status = str(body.get("status") or old["status"]).lower()
            if status not in VALID_STATUSES:
                raise ValueError("无效账号状态")
            days = int(body.get("nurture_days") or old["nurture_days"] or 5)
            if days not in (5, 6, 7):
                raise ValueError("养护天数只能为5、6或7天")
            device_id = int(body["device_id"]) if body.get("device_id") else None
            _validate_device(cur, owner, device_id)
        except (ValueError, TypeError) as exc:
            return ApiOk(ok=False, message=str(exc))
        cur.execute(
            """
            UPDATE SJZQ_PLATFORM_ACCOUNT
               SET OWNER_USER_ID=:owner, DEVICE_ID=:device_id, STATUS=:status,
                   NURTURE_DAYS=:days, MATURE_AT=NURTURE_START+:days,
                   LAST_CHECK_AT=SYSTIMESTAMP, BLOCK_REASON=:reason, REMARK=:remark,
                   UPDATE_TIME=SYSTIMESTAMP
             WHERE ACCOUNT_ID=:id
            """,
            {"owner": owner, "device_id": device_id, "status": status, "days": days,
             "reason": body.get("block_reason"), "remark": body.get("remark"), "id": account_id},
        )
        _check_owner_alert(cur, owner)
        write_op_log(cur, user_id=user["user_id"], username=user["username"], action="account_update", module="account", detail=f"更新账号 #{account_id} 状态={status}", ip=request.client.host if request.client else None)
        return ApiOk()


@router.get("/alerts")
def list_alerts(user=Depends(require_perms("account:view"))):
    with get_conn() as conn:
        cur = conn.cursor()
        sql = "SELECT ALERT_ID, ALERT_TYPE, OWNER_USER_ID, LEVEL_CODE, MESSAGE, STATUS, CREATE_TIME, ACK_TIME FROM SJZQ_ALERT"
        params = {}
        if not _is_admin(user):
            sql += " WHERE OWNER_USER_ID=:owner_id"
            params["owner_id"] = int(user["user_id"])
        sql += " ORDER BY ALERT_ID DESC FETCH FIRST 100 ROWS ONLY"
        cur.execute(sql, params)
        return ApiOk(data=rows_as_dicts(cur))


@router.post("/alerts/{alert_id}/ack")
def ack_alert(alert_id: int, user=Depends(require_perms("account:manage"))):
    with get_conn() as conn:
        cur = conn.cursor()
        sql = "UPDATE SJZQ_ALERT SET STATUS='acked', ACK_TIME=SYSTIMESTAMP, ACK_USER_ID=:ack_user_id WHERE ALERT_ID=:id"
        params = {"ack_user_id": user["user_id"], "id": alert_id}
        if not _is_admin(user):
            sql += " AND OWNER_USER_ID=:owner_id"
            params["owner_id"] = user["user_id"]
        cur.execute(sql, params)
        return ApiOk(ok=cur.rowcount > 0, message="已确认" if cur.rowcount > 0 else "告警不存在")
