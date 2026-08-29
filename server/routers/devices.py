"""设备注册 / 心跳 / 列表。"""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Request

from server.auth_util import require_perms, write_op_log
from server.tenant import require_tenant_perms
from server.device_enrollment import consume, issue, revoke as revoke_enrollment, rotate
from server.cast_state import cast_state
from server.db import get_conn, next_id, rows_as_dicts
from server.ota_meta import latest_payload
from server.media_access import signed_media_url
from server.schemas import ApiOk, DeviceHeartbeatIn, DeviceRegisterIn
from server.services import enrich_device, get_device_by_key, mark_offline_stale
from server.task_state import StateConflict, TaskItemStatus, TaskStatus
from server.task_state_service import close_unfinished_items, require_running_task, state_error_data, transition_task

router = APIRouter(prefix="/api/devices", tags=["devices"])

# 与任务模块同步：暂时关闭强制休息状态。
REST_LOGIC_ENABLED = False


def _ui_status(d: dict) -> str:
    if d.get("status") == "error":
        return "异常"
    if not d.get("online"):
        return "离线"
    if d.get("run_state") == "resting":
        return "休息中"
    # 仅 busy + 有效当前任务 视为采集中（避免幽灵任务 ID）
    if d.get("status") == "busy" and d.get("current_task_id"):
        return "采集中"
    if d.get("status") == "busy":
        return "采集中"
    return "空闲"


@router.post("/register")
def register_device(body: DeviceRegisterIn, request: Request):
    ip = request.client.host if request.client else None
    with get_conn() as conn:
        cur = conn.cursor()
        existed = get_device_by_key(cur, body.device_key, include_revoked=True)
        if existed:
            if existed.get("revoked_at") is not None:
                return ApiOk(ok=False, message="device revoked", data={"error_code": "DEVICE_REVOKED"})
            cur.execute(
                """
                UPDATE SJZQ_DEVICE
                   SET DEVICE_NAME = NVL(:name, DEVICE_NAME),
                       PLATFORM_CODE = :plat,
                       APP_VERSION = NVL(:av, APP_VERSION),
                       OS_VERSION = NVL(:os, OS_VERSION),
                       MODEL = NVL(:model, MODEL),
                       STATUS = 'online',
                       LAST_IP = :ip,
                       LAST_HEARTBEAT = SYSTIMESTAMP,
                       UPDATE_TIME = SYSTIMESTAMP
                 WHERE DEVICE_KEY = :k AND REVOKED_AT IS NULL
                """,
                {
                    "name": body.device_name,
                    "plat": body.platform_code,
                    "av": body.app_version,
                    "os": body.os_version,
                    "model": body.model,
                    "ip": ip,
                    "k": body.device_key,
                },
            )
            if cur.rowcount != 1:
                return ApiOk(ok=False, message="device revoked", data={"error_code": "DEVICE_REVOKED"})
            device = get_device_by_key(cur, body.device_key)
            return ApiOk(message="updated", data=enrich_device(device or {}))

        try:
            device_id = next_id(cur, "SJZQ_SEQ_DEVICE")
            scope = consume(cur, bearer=body.enrollment_token or "", device_id=device_id)
        except ValueError as exc:
            return ApiOk(ok=False, message=str(exc), data={"error_code": str(exc)})
        cur.execute(
            """
            INSERT INTO SJZQ_DEVICE (
                DEVICE_ID, DEVICE_KEY, DEVICE_NAME, PLATFORM_CODE,
                APP_VERSION, OS_VERSION, MODEL, STATUS, LAST_IP, LAST_HEARTBEAT,
                ENTERPRISE_ID, WORKSPACE_ID, ENROLLMENT_TOKEN_ID
            ) VALUES (
                :id, :k, :name, :plat, :av, :os, :model, 'online', :ip, SYSTIMESTAMP,
                :enterprise_id, :workspace_id, :enrollment_token_id
            )
            """,
            {
                "id": device_id,
                "k": body.device_key,
                "name": body.device_name or body.device_key,
                "plat": body.platform_code,
                "av": body.app_version,
                "os": body.os_version,
                "model": body.model,
                "ip": ip,
                "enterprise_id": scope.enterprise_id, "workspace_id": scope.workspace_id,
                "enrollment_token_id": scope.token_id,
            },
        )
        device = get_device_by_key(cur, body.device_key)
        return ApiOk(message="created", data=enrich_device(device or {}))


@router.post("/heartbeat")
def heartbeat(body: DeviceHeartbeatIn, request: Request):
    ip = request.client.host if request.client else None
    with get_conn() as conn:
        cur = conn.cursor()
        device = get_device_by_key(cur, body.device_key)
        if not device:
            return ApiOk(ok=False, message="device not registered", data=None)

        # Client task/status values are observations only. Server assignment is authoritative.
        # A stale/empty heartbeat must never clear or replace CURRENT_TASK_ID/RUN_STATE.
        assigned_task_id = device.get("current_task_id")
        st = "busy" if assigned_task_id is not None else "online"
        cur.execute(
            """
            UPDATE SJZQ_DEVICE
               SET STATUS = :st,
                   APP_VERSION = NVL(:av, APP_VERSION),
                   LAST_IP = :ip,
                   LAST_HEARTBEAT = SYSTIMESTAMP,
                   UPDATE_TIME = SYSTIMESTAMP
             WHERE DEVICE_KEY = :k AND REVOKED_AT IS NULL
            """,
            {
                "st": st,
                "av": body.app_version,
                "ip": ip,
                "k": body.device_key,
            },
        )
        if cur.rowcount != 1:
            return ApiOk(ok=False, message="device revoked", data={"error_code": "DEVICE_REVOKED"})
        device = get_device_by_key(cur, body.device_key)
        data = enrich_device(device or {})
        # App 端指令：投屏请求 / 远程终止
        if data.get("device_id") is not None:
            cast_state.ensure_room(int(data["device_id"]), body.device_key)
        scope = (int(device.get("enterprise_id") or 1), int(device.get("workspace_id") or 1))
        # System Package Installer runs outside the app process. Only the version
        # reported by a later heartbeat confirms a completed installation.
        if body.app_version and body.ota_generation is not None:
            cast_state.confirm_apk_install(body.device_key, body.app_version, body.ota_generation, scope)
        data["commands"] = cast_state.device_commands(body.device_key)
        # 供 App 比对版本：不一致时主界面显示「更新」按钮
        latest = latest_payload(scope)
        if latest.get("has_apk"):
            apk_path = "apk/latest.apk" if scope == (1, 1) else f"apk/{scope[0]}/{scope[1]}/latest.apk"
            latest["apk_url"] = signed_media_url(apk_path, scope[0], scope[1], 900,
                                                  device_id=int(device["device_id"]))
        pending_update = data["commands"].get("update_apk")
        if pending_update:
            apk_path = "apk/latest.apk" if scope == (1, 1) else f"apk/{scope[0]}/{scope[1]}/latest.apk"
            pending_update["apk_url"] = signed_media_url(apk_path, scope[0], scope[1], 900,
                                                          device_id=int(device["device_id"]))
        data["latest_apk"] = latest
        return ApiOk(data=data)


@router.get("")
def list_devices(platform_code: str | None = None, tenant=Depends(require_tenant_perms("device:view"))):
    from server.config import settings

    with get_conn() as conn:
        cur = conn.cursor()
        mark_offline_stale(cur)
        # IS_ALIVE：用数据库时钟判断心跳，避免 Python/Oracle 时区导致误判离线
        sec = int(settings.heartbeat_timeout_sec) + 60
        sql = f"""
            SELECT DEVICE_ID, DEVICE_KEY, DEVICE_NAME, PLATFORM_CODE, APP_VERSION,
                   OS_VERSION, MODEL, STATUS, LAST_IP, LAST_HEARTBEAT,
                   CURRENT_TASK_ID, OWNER_USER_ID, GROUP_NAME,
                   RUN_STATE, RUN_STARTED_AT, REST_UNTIL,
                   NVL(MAX_CONTINUOUS_MIN, 120) AS MAX_CONTINUOUS_MIN,
                   NVL(MIN_REST_MIN, 30) AS MIN_REST_MIN,
                   (SELECT USERNAME FROM SJZQ_USER u WHERE u.USER_ID=SJZQ_DEVICE.OWNER_USER_ID) OWNER_USERNAME,
                   (SELECT REAL_NAME FROM SJZQ_USER u WHERE u.USER_ID=SJZQ_DEVICE.OWNER_USER_ID) OWNER_REAL_NAME,
                   NVL(KEYWORD_RUN_COUNT, 0) AS KEYWORD_RUN_COUNT,
                   CREATE_TIME, UPDATE_TIME,
                   CASE
                     WHEN LAST_HEARTBEAT IS NOT NULL
                      AND LAST_HEARTBEAT >= SYSTIMESTAMP - NUMTODSINTERVAL({sec}, 'SECOND')
                      AND NVL(STATUS, 'offline') NOT IN ('offline', 'error')
                     THEN 1 ELSE 0
                   END AS IS_ALIVE
              FROM SJZQ_DEVICE WHERE ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id
        """
        params: dict = dict(tenant.binds)
        if platform_code:
            sql += " AND PLATFORM_CODE = :p"
            params["p"] = platform_code
        sql += " ORDER BY LAST_HEARTBEAT DESC NULLS LAST, DEVICE_ID DESC"
        cur.execute(sql, params)
        rows = []
        for r in rows_as_dicts(cur):
            d = enrich_device(r)
            if "is_alive" in d:
                d["online"] = int(d.get("is_alive") or 0) == 1
            d["ui_status"] = _ui_status(d)
            d.pop("device_key", None)
            rows.append(d)
        return ApiOk(data=rows)


@router.put("/{device_id}/binding")
def update_binding(
    device_id: int,
    body: dict,
    request: Request,
    user=Depends(require_perms("device:manage")),
    tenant=Depends(require_tenant_perms("device:manage")),
):
    """绑定运营并强制每名运营最多两台设备。"""
    owner_raw = body.get("owner_user_id")
    try:
        owner_id = int(owner_raw) if owner_raw not in (None, "") else None
        max_minutes = int(body.get("max_continuous_min") or 120)
        rest_minutes = int(body.get("min_rest_min") or 30)
    except (TypeError, ValueError):
        return ApiOk(ok=False, message="绑定参数格式错误")
    if tenant.role_code != "super_admin" and owner_id not in (None, int(user["user_id"])):
        return ApiOk(ok=False, message="运营只能绑定本人设备")
    if max_minutes < 15 or max_minutes > 720 or rest_minutes < 5 or rest_minutes > 240:
        return ApiOk(ok=False, message="连续运行须15-720分钟，休息须5-240分钟")
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT COUNT(*) FROM SJZQ_DEVICE WHERE DEVICE_ID=:id
                        AND ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id
                        AND REVOKED_AT IS NULL""", {"id": device_id, **tenant.binds})
        if int(cur.fetchone()[0]) == 0:
            return ApiOk(ok=False, message="设备不存在")
        if owner_id is not None:
            cur.execute(
                """
                SELECT COUNT(*) FROM SJZQ_DEVICE
                 WHERE OWNER_USER_ID=:owner_id AND DEVICE_ID<>:device_id
                   AND ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id AND REVOKED_AT IS NULL
                """,
                {"owner_id": owner_id, "device_id": device_id, **tenant.binds},
            )
            if int(cur.fetchone()[0] or 0) >= 2:
                return ApiOk(ok=False, message="该运营已绑定2台设备，不能继续绑定")
        cur.execute(
            """
            UPDATE SJZQ_DEVICE
               SET OWNER_USER_ID=:owner_id, GROUP_NAME=:group_name,
                   MAX_CONTINUOUS_MIN=:max_minutes, MIN_REST_MIN=:rest_minutes,
                   UPDATE_TIME=SYSTIMESTAMP
             WHERE DEVICE_ID=:device_id AND ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id
            """,
            {"owner_id": owner_id, "group_name": body.get("group_name"),
             "max_minutes": max_minutes, "rest_minutes": rest_minutes, "device_id": device_id, **tenant.binds},
        )
        write_op_log(
            cur, user_id=user["user_id"], username=user["username"],
            action="device_bind", module="device",
            detail=f"设备 {device_id} 绑定运营 {owner_id or '-'}，连续{max_minutes}分钟/休息{rest_minutes}分钟",
            ip=request.client.host if request.client else None,
            **tenant.binds,
        )
        return ApiOk(message="绑定已保存")


@router.post("/{device_id}/abort-task")
def abort_task(device_id: int, request: Request, user=Depends(require_perms("device:manage")),
               tenant=Depends(require_tenant_perms("device:manage"))):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT DEVICE_ID, CURRENT_TASK_ID, DEVICE_NAME FROM SJZQ_DEVICE
                WHERE DEVICE_ID=:id AND ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id
                  AND REVOKED_AT IS NULL FOR UPDATE""",
            {"id": device_id, **tenant.binds},
        )
        row = cur.fetchone()
        if not row:
            return ApiOk(ok=False, message="设备不存在")
        task_id = row[1]
        if task_id:
            try:
                require_running_task(cur, int(task_id), device_id, for_update=True)
                transition_task(cur, int(task_id), TaskStatus.CANCELLED)
                close_unfinished_items(cur, int(task_id), TaskItemStatus.CANCELLED, "远程终止，条目未完成")
                cur.execute("UPDATE SJZQ_TASK SET ERROR_MSG='远程终止', END_TIME=SYSTIMESTAMP WHERE TASK_ID=:id",
                            {"id": int(task_id)})
            except StateConflict as exc:
                return ApiOk(ok=False, message=str(exc), data=state_error_data(exc))
        else:
            return ApiOk(ok=False, message="设备没有当前任务", data={"error_code": "TASK_NOT_FOUND"})
        cur.execute(
            """
            UPDATE SJZQ_DEVICE
               SET CURRENT_TASK_ID=NULL, STATUS='online', RUN_STATE='idle', RUN_STARTED_AT=NULL,
                   REST_UNTIL=NULL, UPDATE_TIME=SYSTIMESTAMP
             WHERE DEVICE_ID=:id AND CURRENT_TASK_ID=:task_id
            """,
            {"id": device_id, "task_id": task_id},
        )
        cast_state.set_abort(device_id, True)
        write_op_log(
            cur,
            user_id=user["user_id"],
            username=user["username"],
            action="device_abort",
            module="device",
            detail=f"终止设备 {device_id} 任务 {task_id}",
            ip=request.client.host if request.client else None,
            **tenant.binds,
        )
        return ApiOk(message="已终止")


@router.get("/{device_id}/tasks")
def device_tasks(device_id: int, tenant=Depends(require_tenant_perms("device:view"))):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT TASK_ID, TASK_NAME, TASK_TYPE, PLATFORM_CODE, STATUS,
                   SUCCESS_COUNT, FAIL_COUNT, START_TIME, END_TIME, CREATE_TIME
              FROM SJZQ_TASK
             WHERE DEVICE_ID = :id AND ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id
             ORDER BY TASK_ID DESC FETCH FIRST 100 ROWS ONLY
            """,
            {"id": device_id, **tenant.binds},
        )
        return ApiOk(data=rows_as_dicts(cur))


@router.post("/enrollment-tokens")
def create_enrollment_token(body: dict, tenant=Depends(require_tenant_perms("device:manage"))):
    minutes = max(5, min(int(body.get("expires_minutes") or 60), 1440))
    with get_conn() as conn:
        token_id, bearer = issue(conn.cursor(), enterprise_id=tenant.enterprise_id,
                                 workspace_id=tenant.workspace_id, issued_by=tenant.user_id,
                                 expires_minutes=minutes)
        return ApiOk(data={"token_id": token_id, "enrollment_token": bearer,
                           "expires_minutes": minutes})


@router.post("/enrollment-tokens/{token_id}/rotate")
def rotate_enrollment_token(token_id: int, body: dict,
                            tenant=Depends(require_tenant_perms("device:manage"))):
    minutes = max(5, min(int(body.get("expires_minutes") or 60), 1440))
    with get_conn() as conn:
        cur = conn.cursor()
        try:
            new_id, bearer = rotate(cur, token_id=token_id, enterprise_id=tenant.enterprise_id,
                                    workspace_id=tenant.workspace_id, issued_by=tenant.user_id,
                                    expires_minutes=minutes)
        except (LookupError, ValueError) as exc:
            return ApiOk(ok=False, message=str(exc), data={"error_code": str(exc)})
        return ApiOk(data={"token_id": new_id, "enrollment_token": bearer,
                           "replaces_token_id": token_id, "expires_minutes": minutes})


@router.post("/enrollment-tokens/{token_id}/revoke")
def revoke_enrollment_token(token_id: int,
                            tenant=Depends(require_tenant_perms("device:manage"))):
    with get_conn() as conn:
        changed = revoke_enrollment(conn.cursor(), token_id=token_id,
                                    enterprise_id=tenant.enterprise_id,
                                    workspace_id=tenant.workspace_id)
        return ApiOk(ok=changed, message="enrollment token 已撤销" if changed else "token 不存在或已失效")


@router.post("/{device_id}/revoke")
async def revoke_device(device_id: int, tenant=Depends(require_tenant_perms("device:manage"))):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT CURRENT_TASK_ID FROM SJZQ_DEVICE WHERE DEVICE_ID=:id
                        AND ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id
                        AND REVOKED_AT IS NULL FOR UPDATE""", {"id": device_id, **tenant.binds})
        row = cur.fetchone()
        if not row:
            return ApiOk(ok=False, message="设备不存在", data={"error_code": "DEVICE_NOT_FOUND"})
        task_id = int(row[0]) if row[0] is not None else None
        if task_id is not None:
            try:
                require_running_task(cur, task_id, device_id, for_update=True)
                transition_task(cur, task_id, TaskStatus.CANCELLED)
                close_unfinished_items(cur, task_id, TaskItemStatus.CANCELLED, "设备已撤销，条目未完成")
                cur.execute("""UPDATE SJZQ_COLLECTION_JOB SET STATUS='cancelled',PAUSE_REQUESTED=0,
                                  LEASE_TOKEN_HASH=NULL,LEASE_EXPIRES_AT=NULL,UPDATE_TIME=SYSTIMESTAMP
                                 WHERE TASK_ID=:task_id AND STATUS IN ('pending','leased','running','paused','retry_wait')""",
                            {"task_id": task_id})
                cur.execute("""UPDATE SJZQ_COLLECTION_LEASE SET STATUS='released',RELEASED_AT=SYSTIMESTAMP,
                                  RELEASE_REASON='device_revoked'
                                 WHERE DEVICE_ID=:device_id AND STATUS='active'""", {"device_id": device_id})
                cur.execute("""UPDATE SJZQ_COLLECTION_ATTEMPT SET STATUS='cancelled',FINISHED_AT=SYSTIMESTAMP,
                                  ERROR_CODE='DEVICE_REVOKED'
                                 WHERE DEVICE_ID=:device_id AND STATUS IN ('leased','running')""", {"device_id": device_id})
            except StateConflict:
                pass
        cur.execute("""UPDATE SJZQ_DEVICE SET REVOKED_AT=SYSTIMESTAMP,REVOKED_BY=:user_id,
                          STATUS='offline',CURRENT_TASK_ID=NULL,ACTIVE_JOB_ID=NULL,ACTIVE_ATTEMPT_ID=NULL,
                          UPDATE_TIME=SYSTIMESTAMP
                         WHERE DEVICE_ID=:id AND ENTERPRISE_ID=:enterprise_id
                           AND WORKSPACE_ID=:workspace_id AND REVOKED_AT IS NULL""",
                    {"id": device_id, "user_id": tenant.user_id, **tenant.binds})
    await cast_state.disconnect_room(device_id, "device revoked")
    return ApiOk(message="设备已撤销")


@router.post("/{device_id}/rotate-key")
async def rotate_device_key(device_id: int, tenant=Depends(require_tenant_perms("device:manage"))):
    replacement = "device_" + secrets.token_urlsafe(24)
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""UPDATE SJZQ_DEVICE SET DEVICE_KEY=:replacement,DEVICE_KEY_ROTATED_AT=SYSTIMESTAMP,
                          UPDATE_TIME=SYSTIMESTAMP WHERE DEVICE_ID=:id AND ENTERPRISE_ID=:enterprise_id
                          AND WORKSPACE_ID=:workspace_id AND REVOKED_AT IS NULL""",
                    {"replacement": replacement, "id": device_id, **tenant.binds})
        if cur.rowcount != 1:
            return ApiOk(ok=False, message="设备不存在", data={"error_code": "DEVICE_NOT_FOUND"})
    await cast_state.disconnect_room(device_id, "device key rotated")
    return ApiOk(data={"device_id": device_id, "device_key": replacement})
