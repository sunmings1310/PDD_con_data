"""设备注册 / 心跳 / 列表。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from server.auth_util import require_perms, write_op_log
from server.cast_state import cast_state
from server.db import get_conn, next_id, rows_as_dicts
from server.ota_meta import latest_payload
from server.schemas import ApiOk, DeviceHeartbeatIn, DeviceRegisterIn
from server.services import enrich_device, get_device_by_key, mark_offline_stale

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
        existed = get_device_by_key(cur, body.device_key)
        if existed:
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
                 WHERE DEVICE_KEY = :k
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
            device = get_device_by_key(cur, body.device_key)
            return ApiOk(message="updated", data=enrich_device(device or {}))

        device_id = next_id(cur, "SJZQ_SEQ_DEVICE")
        cur.execute(
            """
            INSERT INTO SJZQ_DEVICE (
                DEVICE_ID, DEVICE_KEY, DEVICE_NAME, PLATFORM_CODE,
                APP_VERSION, OS_VERSION, MODEL, STATUS, LAST_IP, LAST_HEARTBEAT
            ) VALUES (
                :id, :k, :name, :plat, :av, :os, :model, 'online', :ip, SYSTIMESTAMP
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

        st = (body.status or "online").strip().lower() or "online"
        tid = body.current_task_id
        # 仅允许绑定「进行中」任务；已结束/终止的 ID 不得把设备写回采集中
        if tid is not None:
            cur.execute(
                "SELECT STATUS FROM SJZQ_TASK WHERE TASK_ID = :id",
                {"id": int(tid)},
            )
            row = cur.fetchone()
            task_st = (str(row[0]).lower() if row and row[0] is not None else "")
            if task_st != "running":
                tid = None
                if st == "busy":
                    st = "online"
        elif st != "busy":
            tid = None

        # 关闭休息逻辑时，心跳会清理历史休息窗口并直接回到空闲。
        run_state_sql = (
            "CASE WHEN :tid IS NOT NULL THEN 'running' "
            "WHEN REST_UNTIL IS NOT NULL AND REST_UNTIL>SYSTIMESTAMP THEN 'resting' ELSE 'idle' END"
            if REST_LOGIC_ENABLED else
            "CASE WHEN :tid IS NOT NULL THEN 'running' ELSE 'idle' END"
        )
        rest_until_sql = "REST_UNTIL" if REST_LOGIC_ENABLED else "NULL"
        cur.execute(
            f"""
            UPDATE SJZQ_DEVICE
               SET STATUS = :st,
                   APP_VERSION = NVL(:av, APP_VERSION),
                   LAST_IP = :ip,
                   LAST_HEARTBEAT = SYSTIMESTAMP,
                   CURRENT_TASK_ID = :tid,
                   RUN_STATE = {run_state_sql},
                   RUN_STARTED_AT = CASE
                       WHEN :tid IS NOT NULL THEN NVL(RUN_STARTED_AT, SYSTIMESTAMP)
                       ELSE NULL
                   END,
                   REST_UNTIL = {rest_until_sql},
                   UPDATE_TIME = SYSTIMESTAMP
             WHERE DEVICE_KEY = :k
            """,
            {
                "st": st,
                "av": body.app_version,
                "ip": ip,
                "tid": tid,
                "k": body.device_key,
            },
        )
        device = get_device_by_key(cur, body.device_key)
        data = enrich_device(device or {})
        # App 端指令：投屏请求 / 远程终止
        if data.get("device_id") is not None:
            cast_state.ensure_room(int(data["device_id"]), body.device_key)
        data["commands"] = cast_state.device_commands(body.device_key)
        # 供 App 比对版本：不一致时主界面显示「更新」按钮
        data["latest_apk"] = latest_payload()
        return ApiOk(data=data)


@router.get("")
def list_devices(platform_code: str | None = None, _=Depends(require_perms("device:view"))):
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
              FROM SJZQ_DEVICE
        """
        params: dict = {}
        if platform_code:
            sql += " WHERE PLATFORM_CODE = :p"
            params["p"] = platform_code
        sql += " ORDER BY LAST_HEARTBEAT DESC NULLS LAST, DEVICE_ID DESC"
        cur.execute(sql, params)
        rows = []
        for r in rows_as_dicts(cur):
            d = enrich_device(r)
            if "is_alive" in d:
                d["online"] = int(d.get("is_alive") or 0) == 1
            d["ui_status"] = _ui_status(d)
            rows.append(d)
        return ApiOk(data=rows)


@router.put("/{device_id}/binding")
def update_binding(
    device_id: int,
    body: dict,
    request: Request,
    user=Depends(require_perms("device:manage")),
):
    """绑定运营并强制每名运营最多两台设备。"""
    owner_raw = body.get("owner_user_id")
    try:
        owner_id = int(owner_raw) if owner_raw not in (None, "") else None
        max_minutes = int(body.get("max_continuous_min") or 120)
        rest_minutes = int(body.get("min_rest_min") or 30)
    except (TypeError, ValueError):
        return ApiOk(ok=False, message="绑定参数格式错误")
    if user.get("role_code") != "super_admin" and owner_id not in (None, int(user["user_id"])):
        return ApiOk(ok=False, message="运营只能绑定本人设备")
    if max_minutes < 15 or max_minutes > 720 or rest_minutes < 5 or rest_minutes > 240:
        return ApiOk(ok=False, message="连续运行须15-720分钟，休息须5-240分钟")
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM SJZQ_DEVICE WHERE DEVICE_ID=:id", {"id": device_id})
        if int(cur.fetchone()[0]) == 0:
            return ApiOk(ok=False, message="设备不存在")
        if owner_id is not None:
            cur.execute(
                """
                SELECT COUNT(*) FROM SJZQ_DEVICE
                 WHERE OWNER_USER_ID=:owner_id AND DEVICE_ID<>:device_id
                """,
                {"owner_id": owner_id, "device_id": device_id},
            )
            if int(cur.fetchone()[0] or 0) >= 2:
                return ApiOk(ok=False, message="该运营已绑定2台设备，不能继续绑定")
        cur.execute(
            """
            UPDATE SJZQ_DEVICE
               SET OWNER_USER_ID=:owner_id, GROUP_NAME=:group_name,
                   MAX_CONTINUOUS_MIN=:max_minutes, MIN_REST_MIN=:rest_minutes,
                   UPDATE_TIME=SYSTIMESTAMP
             WHERE DEVICE_ID=:device_id
            """,
            {"owner_id": owner_id, "group_name": body.get("group_name"),
             "max_minutes": max_minutes, "rest_minutes": rest_minutes, "device_id": device_id},
        )
        write_op_log(
            cur, user_id=user["user_id"], username=user["username"],
            action="device_bind", module="device",
            detail=f"设备 {device_id} 绑定运营 {owner_id or '-'}，连续{max_minutes}分钟/休息{rest_minutes}分钟",
            ip=request.client.host if request.client else None,
        )
        return ApiOk(message="绑定已保存")


@router.post("/{device_id}/abort-task")
def abort_task(device_id: int, request: Request, user=Depends(require_perms("device:manage"))):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT DEVICE_ID, CURRENT_TASK_ID, DEVICE_NAME FROM SJZQ_DEVICE WHERE DEVICE_ID=:id",
            {"id": device_id},
        )
        row = cur.fetchone()
        if not row:
            return ApiOk(ok=False, message="设备不存在")
        task_id = row[1]
        if task_id:
            cur.execute(
                """
                UPDATE SJZQ_TASK
                   SET STATUS='failed', ERROR_MSG='远程终止', END_TIME=SYSTIMESTAMP, UPDATE_TIME=SYSTIMESTAMP
                 WHERE TASK_ID=:id AND STATUS='running'
                """,
                {"id": int(task_id)},
            )
        cur.execute(
            """
            UPDATE SJZQ_DEVICE
               SET CURRENT_TASK_ID=NULL, STATUS='online', UPDATE_TIME=SYSTIMESTAMP
             WHERE DEVICE_ID=:id
            """,
            {"id": device_id},
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
        )
        return ApiOk(message="已终止")


@router.get("/{device_id}/tasks")
def device_tasks(device_id: int, _=Depends(require_perms("device:view"))):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT TASK_ID, TASK_NAME, TASK_TYPE, PLATFORM_CODE, STATUS,
                   SUCCESS_COUNT, FAIL_COUNT, START_TIME, END_TIME, CREATE_TIME
              FROM SJZQ_TASK
             WHERE DEVICE_ID = :id
             ORDER BY TASK_ID DESC FETCH FIRST 100 ROWS ONLY
            """,
            {"id": device_id},
        )
        return ApiOk(data=rows_as_dicts(cur))
