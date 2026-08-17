"""任务创建 / 拉取 / 进度 / 完成。"""

from __future__ import annotations

import json
import re
import uuid
import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request, UploadFile, File, Form

from server.auth_util import get_current_user, require_perms, write_op_log
from server.tenant import TenantContext, require_tenant_perms
from server.db import get_conn, next_id, row_as_dict, rows_as_dicts
from server.config import settings
from server.cast_state import cast_state
from server.platforms import TASK_COLLECT, TASK_NURTURE
from server.schemas import ApiOk, TaskCreateIn, TaskFinishIn, TaskProgressIn
from server.services import (
    append_task_log,
    clob_to_str,
    get_device_by_key,
    parse_json_obj,
)
from server.ws_hub import notify_sync
from server.task_state import StateConflict, TaskItemStatus, TaskStatus, task_status, task_storage_status
from server.task_state_service import (
    close_unfinished_items,
    claim_progress_id,
    completed_result,
    get_task_state,
    lock_device,
    require_running_task,
    state_error_data,
    transition_item,
    transition_task,
)
from server.job_service import create_jobs_for_task
from server.quota import ACTIVE_TASK, QuotaExceeded, reserve_and_commit

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _effective_tenant(tenant, user: dict) -> TenantContext:
    if isinstance(tenant, TenantContext): return tenant
    return TenantContext(1,1,int(user["user_id"]),int(user.get("role_id") or 1),
                         str(user.get("role_code") or "legacy"),frozenset(user.get("perms") or ()))

# 临时关闭设备强制休息；改为 True 可恢复连续运行上限与休息窗口。
REST_LOGIC_ENABLED = False


def _has_collection_jobs(cur, task_id: int) -> bool:
    cur.execute(
        "SELECT COUNT(*) FROM SJZQ_COLLECTION_JOB WHERE TASK_ID=:task_id",
        {"task_id": task_id},
    )
    row = cur.fetchone()
    return bool(row and int(row[0] or 0) > 0)


@router.post("")
def create_task(
    body: TaskCreateIn,
    request: Request,
    user=Depends(get_current_user),
    tenant=Depends(require_tenant_perms("task:create")),
):
    tenant = _effective_tenant(tenant, user)
    if body.task_type not in (TASK_COLLECT, TASK_NURTURE):
        return ApiOk(ok=False, message=f"unsupported task_type: {body.task_type}")
    keywords = [k.strip() for k in body.keywords if k and k.strip()]
    with get_conn() as conn:
        cur = conn.cursor()
        if body.device_id is not None and tenant.role_code != "super_admin":
            cur.execute("""SELECT OWNER_USER_ID FROM SJZQ_DEVICE WHERE DEVICE_ID=:id
                            AND ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id""",
                        {"id": body.device_id, **tenant.binds})
            owner = cur.fetchone()
            if not owner or owner[0] is None or int(owner[0]) != int(user["user_id"]):
                return ApiOk(ok=False, message="运营只能向本人绑定设备创建任务")
        task_id = next_id(cur, "SJZQ_SEQ_TASK")
        try:
            reserve_and_commit(
                cur, enterprise_id=tenant.enterprise_id, workspace_id=tenant.workspace_id,
                metric=ACTIVE_TASK, amount=1, resource_type="task", resource_key=str(task_id),
            )
        except QuotaExceeded as exc:
            return ApiOk(ok=False, message=str(exc), data={"error_code": str(exc)})
        keyword_text = "\n".join(keywords)
        config_json = json.dumps(body.config or {}, ensure_ascii=False)
        cur.execute(
            """
            INSERT INTO SJZQ_TASK (
                TASK_ID, TASK_NAME, TASK_TYPE, PLATFORM_CODE, STATUS, PRIORITY,
                DEVICE_ID, KEYWORD_TEXT, TARGET_COUNT, CONFIG_JSON, REVIEW_STATUS,
                CREATE_USER_ID, CREATE_USERNAME, ENTERPRISE_ID, WORKSPACE_ID
            ) VALUES (
                :task_id, :task_name, :tt, :plat, 'pending', :pri,
                :did, :kw, :tc, :cfg, 'pending', :create_user_id, :create_username, :enterprise_id, :workspace_id
            )
            """,
            {
                "task_id": task_id,
                "task_name": body.task_name,
                "tt": body.task_type,
                "plat": body.platform_code,
                "pri": body.priority,
                "did": body.device_id,
                "kw": keyword_text,
                "tc": body.target_count or len(keywords),
                "cfg": config_json,
                "create_user_id": user["user_id"],
                "create_username": user["username"],
                **tenant.binds,
            },
        )
        for i, kw in enumerate(keywords):
            item_id = next_id(cur, "SJZQ_SEQ_TASK_ITEM")
            cur.execute(
                """
                INSERT INTO SJZQ_TASK_ITEM (ITEM_ID, TASK_ID, ROW_INDEX, KEYWORD, STATUS, ENTERPRISE_ID, WORKSPACE_ID)
                VALUES (:id, :tid, :ri, :kw, 'pending', :enterprise_id, :workspace_id)
                """,
                {"id": item_id, "tid": task_id, "ri": i, "kw": kw[:256], **tenant.binds},
            )
        # Phase 2 collection Jobs are materialized in the same transaction as
        # their Task/TaskItem business identity. A retry returns the same
        # JOB_KEY; no Worker lifecycle event can create a new business meaning.
        if body.task_type == TASK_COLLECT:
            create_jobs_for_task(cur, task_id=task_id)
        append_task_log(cur, task_id, f"任务已创建，关键词 {len(keywords)} 个")
        write_op_log(
            cur,
            user_id=user["user_id"],
            username=user["username"],
            action="task_create",
            module="task",
            detail=f"创建任务 #{task_id} {body.task_name}",
            ip=request.client.host if request.client else None,
        )
        return ApiOk(message="created", data={"task_id": task_id})


def _task_ui_status(t: dict) -> str:
    st = t.get("status")
    if st == "pending":
        return "待下发"
    if st == "running":
        return "执行中"
    if st == "succeeded":
        return "全部成功"
    if st == "partially_succeeded":
        return "部分成功"
    if st == "failed":
        return "执行失败"
    if st == "cancelled":
        return "已取消"
    if st == "timed_out":
        return "已超时"
    if st == "done":
        if (t.get("fail_count") or 0) > 0 and (t.get("success_count") or 0) > 0:
            return "部分成功"
        if (t.get("fail_count") or 0) > 0:
            return "全部失败"
        return "全部成功"
    return st or "-"


def _normalize_task_output(t: dict) -> None:
    try:
        t["status"] = task_status(str(t.get("status") or "")).value
    except ValueError:
        pass


@router.get("")
def list_tasks(
    status: str | None = None,
    platform_code: str | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    user=Depends(get_current_user),
    tenant=Depends(require_tenant_perms("task:view")),
):
    with get_conn() as conn:
        cur = conn.cursor()
        select_sql = """
            SELECT TASK_ID, TASK_NAME, TASK_TYPE, PLATFORM_CODE, STATUS, PRIORITY,
                   DEVICE_ID, TARGET_COUNT, SUCCESS_COUNT, FAIL_COUNT, ERROR_MSG,
                   START_TIME, END_TIME, CREATE_TIME, UPDATE_TIME,
                   CREATE_USER_ID, CREATE_USERNAME, REVIEW_STATUS,
                   REVIEW_USERNAME, REVIEW_TIME, REVIEW_REMARK
             FROM SJZQ_TASK
             WHERE ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id
        """
        where_sql = ""
        params: dict = dict(tenant.binds)
        if status:
            where_sql += " AND STATUS = :st"
            try:
                params["st"] = task_storage_status(status)
            except ValueError:
                return ApiOk(ok=False, message=f"invalid task status filter: {status}",
                             data={"error_code": "INVALID_TASK_STATUS"})
        if platform_code:
            where_sql += " AND PLATFORM_CODE = :p"
            params["p"] = platform_code
        cur.execute("SELECT COUNT(*) FROM SJZQ_TASK WHERE ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id" + where_sql, params)
        total = int(cur.fetchone()[0])
        page_params = {**params, "offset": (page - 1) * limit, "limit": limit}
        cur.execute(
            select_sql + where_sql
            + " ORDER BY CREATE_TIME DESC, TASK_ID DESC"
            + " OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY",
            page_params,
        )
        rows = rows_as_dicts(cur)
        for t in rows:
            _normalize_task_output(t)
            t["ui_status"] = _task_ui_status(t)
            _add_task_capabilities(t)
            t["can_review"] = tenant.role_code == "super_admin" or int(t.get("create_user_id") or 0) == int(user["user_id"])
        return ApiOk(data={"total": total, "page": page, "limit": limit, "items": rows})


@router.get("/{task_id}")
def get_task(task_id: int, user=Depends(get_current_user), tenant=Depends(require_tenant_perms("task:view"))):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT TASK_ID, TASK_NAME, TASK_TYPE, PLATFORM_CODE, STATUS, PRIORITY,
                   DEVICE_ID, KEYWORD_TEXT, TARGET_COUNT, SUCCESS_COUNT, FAIL_COUNT,
                   CONFIG_JSON, ERROR_MSG, START_TIME, END_TIME, CREATE_TIME,
                   CREATE_USER_ID, CREATE_USERNAME, REVIEW_STATUS, REVIEW_USER_ID,
                   REVIEW_USERNAME, REVIEW_TIME, REVIEW_REMARK
              FROM SJZQ_TASK WHERE TASK_ID=:id AND ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id
            """,
            {"id": task_id, **tenant.binds},
        )
        task = row_as_dict(cur)
        if not task:
            return ApiOk(ok=False, message="task not found")
        task["keyword_text"] = clob_to_str(task.get("keyword_text"))
        task["config_json"] = clob_to_str(task.get("config_json"))
        _normalize_task_output(task)
        cur.execute(
            """
            SELECT ITEM_ID, ROW_INDEX, KEYWORD, TARGET_SPEC, TARGET_APPROVAL,
                   TARGET_NAME, TARGET_MANUFACTURER, ORIGINAL_ROW_JSON,
                   STATUS, PRODUCT_ID, MESSAGE, UPDATE_TIME
              FROM SJZQ_TASK_ITEM
             WHERE TASK_ID=:id AND ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id
             ORDER BY ROW_INDEX
            """,
            {"id": task_id, **tenant.binds},
        )
        task["items"] = rows_as_dicts(cur)
        cur.execute(
            """
            SELECT LOG_ID, DEVICE_ID, LEVEL_CODE, MESSAGE, CREATE_TIME
              FROM SJZQ_TASK_LOG
             WHERE TASK_ID=:id AND ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id
             ORDER BY LOG_ID DESC
             FETCH FIRST 100 ROWS ONLY
            """,
            {"id": task_id, **tenant.binds},
        )
        try:
            task["logs"] = rows_as_dicts(cur)
        except Exception:
            cur.execute(
                """
                SELECT LOG_ID, DEVICE_ID, LEVEL_CODE, MESSAGE, CREATE_TIME
                  FROM SJZQ_TASK_LOG WHERE TASK_ID = :id ORDER BY LOG_ID DESC
                """,
                {"id": task_id},
            )
            task["logs"] = rows_as_dicts(cur)[:100]
        task["ui_status"] = _task_ui_status(task)
        _add_task_capabilities(task)
        task["can_review"] = tenant.role_code == "super_admin" or int(task.get("create_user_id") or 0) == int(user["user_id"])
        task["can_manage_results"] = task["can_review"]
        cur.execute("""
            SELECT ANOMALY_ID, DEVICE_ID, ACTION_NAME, MESSAGE, PAGE_TEXT,
                   SCREENSHOT_PATH, CONSECUTIVE_COUNT, CREATE_TIME
              FROM SJZQ_TASK_ANOMALY WHERE TASK_ID=:id
             ORDER BY ANOMALY_ID DESC FETCH FIRST 200 ROWS ONLY
        """, {"id": task_id})
        anomalies = rows_as_dicts(cur)
        for item in anomalies:
            rel = item.get("screenshot_path") or ""
            item["screenshot_url"] = f"/media/{rel}" if rel else ""
        task["anomalies"] = anomalies
        return ApiOk(data=task)


@router.post("/{task_id}/requeue-failed")
def requeue_failed_items(
    task_id: int,
    body: dict,
    request: Request,
    user=Depends(require_perms("task:create")),
    tenant=Depends(require_tenant_perms("task:create")),
):
    tenant = _effective_tenant(tenant, user)
    """重新下发失败/取消明细，并完整复制原匹配目标与任务配置。"""
    include_cancelled = bool(body.get("include_cancelled", True))
    dry_run = bool(body.get("dry_run", False))
    statuses = ["failed"] + (["cancelled"] if include_cancelled else [])
    status_sql = "'failed','cancelled'" if include_cancelled else "'failed'"
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT TASK_NAME, TASK_TYPE, PLATFORM_CODE, PRIORITY, DEVICE_ID,
                   CONFIG_JSON, CREATE_USER_ID
              FROM SJZQ_TASK WHERE TASK_ID=:id AND ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id
            """,
            {"id": task_id, **tenant.binds},
        )
        source = row_as_dict(cur)
        if not source:
            return ApiOk(ok=False, message="原任务不存在")
        if tenant.role_code != "super_admin" and int(source.get("create_user_id") or 0) != int(user["user_id"]):
            return ApiOk(ok=False, message="运营只能重新下发本人创建的任务")

        device_id = source.get("device_id")
        if device_id is not None and tenant.role_code != "super_admin":
            cur.execute("SELECT OWNER_USER_ID FROM SJZQ_DEVICE WHERE DEVICE_ID=:id", {"id": device_id})
            owner = cur.fetchone()
            if not owner or owner[0] is None or int(owner[0]) != int(user["user_id"]):
                return ApiOk(ok=False, message="原任务设备当前未绑定给本人，请先重新绑定设备")

        cur.execute(
            f"""
            SELECT ROW_INDEX, KEYWORD, TARGET_SPEC, TARGET_APPROVAL,
                   TARGET_NAME, TARGET_MANUFACTURER, ORIGINAL_ROW_JSON
              FROM SJZQ_TASK_ITEM
             WHERE TASK_ID=:id AND STATUS IN ({status_sql})
             ORDER BY ROW_INDEX
            """,
            {"id": task_id},
        )
        retry_items = rows_as_dicts(cur)
        if not retry_items:
            return ApiOk(ok=False, message=f"原任务没有可重新下发的{'/'.join(statuses)}条目")

        # 兼容历史错误重采任务（例如 52/53）：旧前端只复制 keyword，目标字段已经丢失。
        # 从任务名中的「原任务N」定位祖先任务，再按关键词逐条恢复四字段和原始 Excel 行。
        recovered_from_task_id = None
        has_any_target = any(
            item.get("target_spec") or item.get("target_approval") or
            item.get("target_name") or item.get("target_manufacturer")
            for item in retry_items
        )
        if not has_any_target:
            source_name = str(source.get("task_name") or "")
            ancestor_match = re.search(r"原任务\s*(\d+)", source_name)
            if ancestor_match:
                ancestor_id = int(ancestor_match.group(1))
                cur.execute(
                    """
                    SELECT ROW_INDEX, KEYWORD, TARGET_SPEC, TARGET_APPROVAL,
                           TARGET_NAME, TARGET_MANUFACTURER, ORIGINAL_ROW_JSON
                      FROM SJZQ_TASK_ITEM
                     WHERE TASK_ID=:id
                     ORDER BY ROW_INDEX
                    """,
                    {"id": ancestor_id},
                )
                ancestor_items = rows_as_dicts(cur)
                buckets: dict[str, list[dict]] = {}
                for ancestor_item in ancestor_items:
                    key = str(ancestor_item.get("keyword") or "").strip()
                    buckets.setdefault(key, []).append(ancestor_item)
                recovered = 0
                for item in retry_items:
                    key = str(item.get("keyword") or "").strip()
                    candidates = buckets.get(key) or []
                    if not candidates:
                        continue
                    ancestor_item = candidates.pop(0)
                    for field in (
                        "target_spec", "target_approval", "target_name",
                        "target_manufacturer", "original_row_json",
                    ):
                        if not item.get(field):
                            item[field] = ancestor_item.get(field)
                    if any(item.get(field) for field in (
                        "target_spec", "target_approval", "target_name", "target_manufacturer",
                    )):
                        recovered += 1
                if recovered:
                    recovered_from_task_id = ancestor_id
                    cur.execute("SELECT CONFIG_JSON FROM SJZQ_TASK WHERE TASK_ID=:id", {"id": ancestor_id})
                    ancestor_task = cur.fetchone()
                    if ancestor_task and clob_to_str(ancestor_task[0]):
                        source["config_json"] = ancestor_task[0]

        preview = [
            {
                "row_index": item.get("row_index"),
                "keyword": item.get("keyword"),
                "target_spec": item.get("target_spec"),
                "target_approval": item.get("target_approval"),
                "target_name": item.get("target_name"),
                "target_manufacturer": item.get("target_manufacturer"),
                "has_original_row": bool(clob_to_str(item.get("original_row_json"))),
            }
            for item in retry_items
        ]
        match_target_count = sum(
            1 for item in retry_items
            if item.get("target_spec") or item.get("target_approval") or item.get("target_name") or item.get("target_manufacturer")
        )
        if dry_run:
            return ApiOk(
                message="dry run",
                data={
                    "source_task_id": task_id,
                    "count": len(retry_items),
                    "match_target_count": match_target_count,
                    "recovered_from_task_id": recovered_from_task_id,
                    "items": preview,
                },
            )

        new_task_id = next_id(cur, "SJZQ_SEQ_TASK")
        try:
            reserve_and_commit(
                cur, enterprise_id=tenant.enterprise_id, workspace_id=tenant.workspace_id,
                metric=ACTIVE_TASK, amount=1, resource_type="task", resource_key=str(new_task_id),
            )
        except QuotaExceeded as exc:
            return ApiOk(ok=False, message=str(exc), data={"error_code": str(exc)})
        keywords = [str(item.get("keyword") or "").strip() for item in retry_items]
        config_json = clob_to_str(source.get("config_json")) or "{}"
        new_name = str(body.get("task_name") or f"重采-原任务{task_id}")[:200]
        cur.execute(
            """
            INSERT INTO SJZQ_TASK (
                TASK_ID, TASK_NAME, TASK_TYPE, PLATFORM_CODE, STATUS, PRIORITY,
                DEVICE_ID, KEYWORD_TEXT, TARGET_COUNT, CONFIG_JSON, REVIEW_STATUS,
                CREATE_USER_ID, CREATE_USERNAME, ENTERPRISE_ID, WORKSPACE_ID
            ) VALUES (
                :task_id, :task_name, :task_type, :platform, 'pending', :priority,
                :device_id, :keywords, :target_count, :config_json, 'pending',
                :user_id, :username, :enterprise_id, :workspace_id
            )
            """,
            {
                "task_id": new_task_id,
                "task_name": new_name,
                "task_type": source.get("task_type") or TASK_COLLECT,
                "platform": source.get("platform_code"),
                "priority": source.get("priority") or 5,
                "device_id": device_id,
                "keywords": "\n".join(keywords),
                "target_count": len(retry_items),
                "config_json": config_json,
                "user_id": user["user_id"],
                "username": user["username"],
                **tenant.binds,
            },
        )
        for index, item in enumerate(retry_items):
            item_id = next_id(cur, "SJZQ_SEQ_TASK_ITEM")
            cur.execute(
                """
                INSERT INTO SJZQ_TASK_ITEM (
                    ITEM_ID, TASK_ID, ROW_INDEX, KEYWORD, TARGET_SPEC, TARGET_APPROVAL,
                    TARGET_NAME, TARGET_MANUFACTURER, ORIGINAL_ROW_JSON, STATUS, ENTERPRISE_ID, WORKSPACE_ID
                ) VALUES (
                    :item_id, :task_id, :row_index, :keyword, :target_spec, :target_approval,
                    :target_name, :target_manufacturer, :original_row_json, 'pending', :enterprise_id, :workspace_id
                )
                """,
                {
                    "item_id": item_id,
                    "task_id": new_task_id,
                    "row_index": index,
                    "keyword": str(item.get("keyword") or "")[:256],
                    "target_spec": item.get("target_spec"),
                    "target_approval": item.get("target_approval"),
                    "target_name": item.get("target_name"),
                    "target_manufacturer": item.get("target_manufacturer"),
                    "original_row_json": clob_to_str(item.get("original_row_json")),
                    **tenant.binds,
                },
            )
        append_task_log(
            cur,
            new_task_id,
            f"从任务 #{task_id} 重新下发 {len(retry_items)} 条，保留匹配目标 {match_target_count} 条" +
            (f"（由祖先任务 #{recovered_from_task_id} 恢复）" if recovered_from_task_id else ""),
        )
        append_task_log(cur, task_id, f"失败/取消条目已重新下发为任务 #{new_task_id}")
        write_op_log(
            cur,
            user_id=user["user_id"],
            username=user["username"],
            action="task_requeue_failed",
            module="task",
            detail=f"任务 #{task_id} 失败/取消条目重采为 #{new_task_id}，共 {len(retry_items)} 条",
            ip=request.client.host if request.client else None,
        )
        return ApiOk(
            message="已重新下发并保留原匹配目标",
            data={
                "task_id": new_task_id,
                "source_task_id": task_id,
                "count": len(retry_items),
                "match_target_count": match_target_count,
                "recovered_from_task_id": recovered_from_task_id,
            },
        )


@router.post("/{task_id}/anomalies")
async def upload_anomaly(
    task_id: int,
    device_key: str = Form(...),
    action_name: str = Form("action"),
    message: str = Form(""),
    page_text: str = Form(""),
    consecutive_count: int = Form(1),
    screenshot: UploadFile | None = File(None),
):
    with get_conn() as conn:
        cur = conn.cursor()
        device = get_device_by_key(cur, device_key)
        if not device:
            return ApiOk(ok=False, message="device not registered")

        cur.execute("SELECT COUNT(*) FROM SJZQ_TASK WHERE TASK_ID=:id", {"id": task_id})
        if int(cur.fetchone()[0] or 0) == 0:
            return ApiOk(ok=False, message="task not found")
        rel_path = None
        if screenshot is not None:
            suffix = Path(screenshot.filename or "screen.jpg").suffix.lower() or ".jpg"
            rel = Path("anomalies") / str(task_id) / f"{uuid.uuid4().hex}{suffix}"
            dest = Path(settings.image_dir) / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(await screenshot.read())
            rel_path = rel.as_posix()
        anomaly_id = next_id(cur, "SJZQ_SEQ_TASK_ANOMALY")
        cur.execute("""
            INSERT INTO SJZQ_TASK_ANOMALY
            (ANOMALY_ID, TASK_ID, DEVICE_ID, ACTION_NAME, MESSAGE, PAGE_TEXT,
             SCREENSHOT_PATH, CONSECUTIVE_COUNT)
            VALUES (:id, :tid, :did, :action, :msg, :page_text, :shot, :cnt)
        """, {"id": anomaly_id, "tid": task_id, "did": device["device_id"],
              "action": action_name[:128], "msg": message[:2000], "page_text": page_text[:12000],
              "shot": rel_path, "cnt": max(1, consecutive_count)})
        append_task_log(cur, task_id, f"异常记录 #{anomaly_id} action={action_name} 连续={consecutive_count}",
                        device_id=device["device_id"], level="error")
        return ApiOk(message="anomaly saved", data={"anomaly_id": anomaly_id, "screenshot_path": rel_path})


@router.post("/{task_id}/review")
def review_task(
    task_id: int,
    body: dict,
    request: Request,
    user=Depends(get_current_user),
    tenant=Depends(require_tenant_perms("task:review")),
):
    tenant = _effective_tenant(tenant, user)
    decision = str(body.get("decision") or "").lower()
    if decision not in {"approved", "rejected"}:
        return ApiOk(ok=False, message="审核结果只能为 approved 或 rejected")
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT CREATE_USER_ID,STATUS FROM SJZQ_TASK WHERE TASK_ID=:id
                        AND ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id""",
                    {"id": task_id, **tenant.binds})
        row = cur.fetchone()
        if not row:
            return ApiOk(ok=False, message="任务不存在")
        if tenant.role_code != "super_admin" and int(row[0] or 0) != int(user["user_id"]):
            return ApiOk(ok=False, message="运营只能审核本人创建的任务")
        if str(row[1]) != "pending":
            return ApiOk(ok=False, message="仅待下发任务可以审核")
        cur.execute(
            """
            UPDATE SJZQ_TASK
               SET REVIEW_STATUS=:decision, REVIEW_USER_ID=:reviewer_id,
                   REVIEW_USERNAME=:username, REVIEW_TIME=SYSTIMESTAMP,
                   REVIEW_REMARK=:remark, UPDATE_TIME=SYSTIMESTAMP
             WHERE TASK_ID=:id AND STATUS='pending' AND REVIEW_STATUS='pending'
            """,
            {"decision": decision, "reviewer_id": user["user_id"], "username": user["username"],
             "remark": str(body.get("remark") or "")[:500] or None, "id": task_id},
        )
        if cur.rowcount != 1:
            return ApiOk(ok=False, message="审核状态已变化", data={"error_code": "REVIEW_STATE_CONFLICT"})
        append_task_log(cur, task_id, f"任务审核：{decision}，审核人={user['username']}")
        write_op_log(
            cur, user_id=user["user_id"], username=user["username"], action="task_review",
            module="task", detail=f"审核任务 #{task_id} {decision}",
            ip=request.client.host if request.client else None,
        )
        return ApiOk(message="审核完成")


@router.post("/{task_id}/cancel")
def cancel_task(
    task_id: int,
    request: Request,
    user=Depends(get_current_user),
    tenant=Depends(require_tenant_perms("task:create")),
):
    """Cancel a pending/running task through the authoritative state machine."""
    tenant = _effective_tenant(tenant, user)
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT CREATE_USER_ID,DEVICE_ID FROM SJZQ_TASK WHERE TASK_ID=:id
                        AND ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id""",
                    {"id": task_id, **tenant.binds})
        row = cur.fetchone()
        if not row:
            return ApiOk(ok=False, message="任务不存在", data={"error_code": "TASK_NOT_FOUND"})
        if tenant.role_code != "super_admin" and int(row[0] or 0) != int(user["user_id"]):
            return ApiOk(ok=False, message="运营只能取消本人创建的任务")
        try:
            if row[1] is not None:
                lock_device(cur, int(row[1]))
            _, changed = transition_task(cur, task_id, TaskStatus.CANCELLED)
        except StateConflict as exc:
            if exc.current == TaskStatus.CANCELLED.value:
                return ApiOk(message="already cancelled", data={"status": "cancelled", "idempotent": True})
            return ApiOk(ok=False, message=str(exc), data=state_error_data(exc))
        if changed:
            cur.execute(
                "SELECT JOB_ID FROM SJZQ_COLLECTION_JOB WHERE TASK_ID=:task_id FOR UPDATE",
                {"task_id": task_id},
            )
            phase2_job_ids = [int(value[0]) for value in cur.fetchall()]
            if phase2_job_ids:
                cur.execute(
                    """UPDATE SJZQ_COLLECTION_ATTEMPT SET STATUS='cancelled', FINISHED_AT=SYSTIMESTAMP,
                              ERROR_CLASS='business_rejection', ERROR_CODE='TASK_CANCELLED', RETRYABLE=0
                         WHERE JOB_ID IN (SELECT JOB_ID FROM SJZQ_COLLECTION_JOB WHERE TASK_ID=:task_id)
                           AND STATUS IN ('leased','running')""",
                    {"task_id": task_id},
                )
                cur.execute(
                    """UPDATE SJZQ_COLLECTION_LEASE SET STATUS='released', RELEASED_AT=SYSTIMESTAMP,
                              RELEASE_REASON='task_cancelled'
                         WHERE JOB_ID IN (SELECT JOB_ID FROM SJZQ_COLLECTION_JOB WHERE TASK_ID=:task_id)
                           AND STATUS='active'""",
                    {"task_id": task_id},
                )
                cur.execute(
                    """UPDATE SJZQ_COLLECTION_JOB SET STATUS='cancelled', ACTIVE_ATTEMPT_ID=NULL,
                              LEASE_TOKEN_HASH=NULL, LEASE_EXPIRES_AT=NULL, DEVICE_ID=NULL,
                              PAUSE_REQUESTED=0, UPDATE_TIME=SYSTIMESTAMP
                         WHERE TASK_ID=:task_id
                           AND STATUS IN ('pending','leased','running','paused','retry_wait')""",
                    {"task_id": task_id},
                )
            close_unfinished_items(cur, task_id, TaskItemStatus.CANCELLED, "任务已取消，条目未完成")
            cur.execute("UPDATE SJZQ_TASK SET END_TIME=SYSTIMESTAMP WHERE TASK_ID=:id", {"id": task_id})
            if row[1] is not None:
                cur.execute(
                    """UPDATE SJZQ_DEVICE SET CURRENT_TASK_ID=NULL, STATUS='online', RUN_STATE='idle',
                              ACTIVE_JOB_ID=NULL, ACTIVE_ATTEMPT_ID=NULL,
                              RUN_STARTED_AT=NULL, REST_UNTIL=NULL, UPDATE_TIME=SYSTIMESTAMP
                         WHERE DEVICE_ID=:did AND CURRENT_TASK_ID=:tid""",
                    {"did": int(row[1]), "tid": task_id},
                )
                cast_state.set_abort(int(row[1]), True)
            append_task_log(cur, task_id, f"任务取消，操作人={user['username']}")
            write_op_log(cur, user_id=user["user_id"], username=user["username"], action="task_cancel",
                         module="task", detail=f"取消任务 #{task_id}",
                         ip=request.client.host if request.client else None)
        return ApiOk(message="已取消", data={"status": "cancelled"})


@router.post("/pull")
def pull_task(device_key: str, platform_code: str | None = None):
    """App 拉取下一条待执行任务。"""
    with get_conn() as conn:
        cur = conn.cursor()
        device = get_device_by_key(cur, device_key)
        if not device:
            return ApiOk(ok=False, message="device not registered")

        # Serialize pull requests for one device. The lock, task claim and device
        # occupancy update share the get_conn transaction.
        cur.execute(
            """SELECT CURRENT_TASK_ID, RUN_STATE, REST_UNTIL, RUN_STARTED_AT,
                      NVL(MAX_CONTINUOUS_MIN,120), NVL(MIN_REST_MIN,30)
                 FROM SJZQ_DEVICE WHERE DEVICE_ID=:id FOR UPDATE""",
            {"id": device["device_id"]},
        )
        locked_device = cur.fetchone()
        if not locked_device:
            return ApiOk(ok=False, message="device not registered")
        if locked_device[0] is not None:
            return ApiOk(message="device already occupied", data=None)

        if REST_LOGIC_ENABLED:
            _, _, rest_until, run_started, max_minutes, rest_minutes = locked_device
            cur.execute(
                "SELECT CASE WHEN :rest_until IS NOT NULL AND :rest_until>SYSTIMESTAMP THEN 1 ELSE 0 END FROM DUAL",
                {"rest_until": rest_until},
            )
            resting = cur.fetchone()[0]
            if int(resting or 0) == 1:
                cur.execute("UPDATE SJZQ_DEVICE SET RUN_STATE='resting', STATUS='online' WHERE DEVICE_ID=:id", {"id": device["device_id"]})
                return ApiOk(message=f"device resting until {rest_until}", data=None)
            if run_started is not None:
                cur.execute(
                    "SELECT CASE WHEN :started <= SYSTIMESTAMP-NUMTODSINTERVAL(:mins,'MINUTE') THEN 1 ELSE 0 END FROM DUAL",
                    {"started": run_started, "mins": int(max_minutes)},
                )
                if int(cur.fetchone()[0] or 0) == 1:
                    cur.execute(
                        """
                        UPDATE SJZQ_DEVICE SET RUN_STATE='resting', STATUS='online', RUN_STARTED_AT=NULL,
                               REST_UNTIL=SYSTIMESTAMP+NUMTODSINTERVAL(:rest_minutes,'MINUTE')
                         WHERE DEVICE_ID=:id
                        """,
                        {"rest_minutes": int(rest_minutes), "id": device["device_id"]},
                    )
                    return ApiOk(message="continuous runtime limit reached", data=None)
        else:
            cur.execute(
                "UPDATE SJZQ_DEVICE SET REST_UNTIL=NULL, RUN_STATE=CASE WHEN CURRENT_TASK_ID IS NULL THEN 'idle' ELSE 'running' END WHERE DEVICE_ID=:id",
                {"id": device["device_id"]},
            )

        # 优先指定设备的任务，其次同平台空闲任务
        cur.execute(
            """
            SELECT TASK_ID FROM SJZQ_TASK
             WHERE STATUS = 'pending'
               AND NVL(REVIEW_STATUS, 'approved') = 'approved'
               AND NOT EXISTS (
                     SELECT 1 FROM SJZQ_COLLECTION_JOB j
                      WHERE j.TASK_ID=SJZQ_TASK.TASK_ID
                   )
               AND (DEVICE_ID = :did OR DEVICE_ID IS NULL)
               AND (:plat IS NULL OR PLATFORM_CODE = :plat)
             ORDER BY
               CASE WHEN DEVICE_ID = :did THEN 0 ELSE 1 END,
               PRIORITY ASC,
               CREATE_TIME ASC
             FETCH FIRST 1 ROWS ONLY
            """,
            {
                "did": device["device_id"],
                "plat": platform_code or device.get("platform_code"),
            },
        )
        row = cur.fetchone()
        if not row:
            # 兼容老 SQL
            cur.execute(
                """
                SELECT TASK_ID FROM SJZQ_TASK
                 WHERE STATUS = 'pending'
                   AND NVL(REVIEW_STATUS, 'approved') = 'approved'
                   AND NOT EXISTS (
                         SELECT 1 FROM SJZQ_COLLECTION_JOB j
                          WHERE j.TASK_ID=SJZQ_TASK.TASK_ID
                       )
                   AND (DEVICE_ID = :did OR DEVICE_ID IS NULL)
                   AND (:plat IS NULL OR PLATFORM_CODE = :plat)
                 ORDER BY PRIORITY ASC, CREATE_TIME ASC
                """,
                {
                    "did": device["device_id"],
                    "plat": platform_code or device.get("platform_code"),
                },
            )
            row = cur.fetchone()
        if not row:
            return ApiOk(message="no task", data=None)

        task_id = int(row[0])
        try:
            transition_task(cur, task_id, TaskStatus.RUNNING)
        except StateConflict:
            return ApiOk(message="no task", data=None)
        cur.execute("""UPDATE SJZQ_TASK SET DEVICE_ID=:did,
                              START_TIME=NVL(START_TIME,SYSTIMESTAMP), UPDATE_TIME=SYSTIMESTAMP
                         WHERE TASK_ID=:id AND STATUS='running'""",
                    {"did": device["device_id"], "id": task_id})

        cur.execute(
            """
            UPDATE SJZQ_DEVICE
               SET CURRENT_TASK_ID = :tid, STATUS = 'busy', RUN_STATE='running',
                   RUN_STARTED_AT=NVL(RUN_STARTED_AT, SYSTIMESTAMP), REST_UNTIL=NULL,
                   UPDATE_TIME = SYSTIMESTAMP
             WHERE DEVICE_ID = :did AND CURRENT_TASK_ID IS NULL
            """,
            {"tid": task_id, "did": device["device_id"]},
        )
        if cur.rowcount != 1:
            raise StateConflict("DEVICE_OCCUPANCY_RACE", "occupied", str(task_id))

        cur.execute(
            """
            SELECT TASK_ID, TASK_NAME, TASK_TYPE, PLATFORM_CODE, KEYWORD_TEXT, CONFIG_JSON
              FROM SJZQ_TASK WHERE TASK_ID = :id
            """,
            {"id": task_id},
        )
        task = row_as_dict(cur) or {}
        kw_text = clob_to_str(task.get("keyword_text")) or ""
        keywords = [x.strip() for x in kw_text.splitlines() if x.strip()]
        config = parse_json_obj(clob_to_str(task.get("config_json")))
        cur.execute(
            """
            SELECT ITEM_ID, ROW_INDEX, KEYWORD, TARGET_SPEC, TARGET_APPROVAL,
                   TARGET_NAME, TARGET_MANUFACTURER, ORIGINAL_ROW_JSON, STATUS
              FROM SJZQ_TASK_ITEM WHERE TASK_ID = :id ORDER BY ROW_INDEX
            """,
            {"id": task_id},
        )
        items = rows_as_dicts(cur)
        append_task_log(
            cur, task_id, f"设备 {device.get('device_name') or device_key} 已领取任务",
            device_id=device["device_id"],
        )
        return ApiOk(
            data={
                "task_id": task_id,
                "task_name": task.get("task_name"),
                "task_type": task.get("task_type"),
                "platform_code": task.get("platform_code"),
                "keywords": keywords,
                "config": config,
                "items": items,
            }
        )


@router.post("/progress")
def task_progress(body: TaskProgressIn):
    with get_conn() as conn:
        cur = conn.cursor()
        device = get_device_by_key(cur, body.device_key)
        if not device:
            return ApiOk(ok=False, message="device not registered")
        try:
            lock_device(cur, int(device["device_id"]))
            require_running_task(cur, body.task_id, device["device_id"], for_update=True)
        except StateConflict as exc:
            return ApiOk(ok=False, message=str(exc), data=state_error_data(exc))
        if _has_collection_jobs(cur, body.task_id):
            return ApiOk(
                ok=False,
                message="Phase 2 Job progress requires a current lease/checkpoint",
                data={"error_code": "LEASE_REQUIRED"},
            )
        item_status = (body.item_status or "").strip().lower()
        has_delta = bool(body.success_delta or body.fail_delta or body.keyword_delta)
        if has_delta:
            if not body.progress_id:
                return ApiOk(ok=False, message="delta progress requires progress_id",
                             data={"error_code": "PROGRESS_ID_REQUIRED"})
            if not claim_progress_id(cur, body.progress_id, body.task_id, int(device["device_id"])):
                return ApiOk(message="duplicate progress ignored",
                             data={"progress_id": body.progress_id, "idempotent": True})
        if body.item_id is not None and item_status:
            # Deprecated compatibility: old Agent used done and failed for match/no-match.
            item_status = {"done": "succeeded"}.get(item_status, item_status)
            try:
                transition_item(cur, body.task_id, body.item_id, item_status,
                                message=body.message, product_id=body.product_id)
            except (StateConflict, ValueError) as exc:
                data = state_error_data(exc) if isinstance(exc, StateConflict) else {"error_code": "INVALID_ITEM_STATUS"}
                return ApiOk(ok=False, message=str(exc), data=data)
            # 明细状态是匹配任务的真实进度来源，按明细重算以避免重复回调导致计数漂移。
            cur.execute(
                """
                UPDATE SJZQ_TASK
                   SET SUCCESS_COUNT = (
                           SELECT COUNT(*) FROM SJZQ_TASK_ITEM
                             WHERE TASK_ID = :task_id AND STATUS IN ('succeeded','done')
                       ),
                       FAIL_COUNT = (
                           SELECT COUNT(*) FROM SJZQ_TASK_ITEM
                             WHERE TASK_ID = :task_id AND STATUS IN ('failed','not_matched')
                       ),
                       UPDATE_TIME = SYSTIMESTAMP
                 WHERE TASK_ID = :task_id
                """,
                {"task_id": body.task_id},
            )
        else:
            cur.execute(
                """
                UPDATE SJZQ_TASK
                   SET SUCCESS_COUNT = SUCCESS_COUNT + :sd,
                       FAIL_COUNT = FAIL_COUNT + :fd,
                       UPDATE_TIME = SYSTIMESTAMP
                 WHERE TASK_ID = :id
                """,
                {"sd": body.success_delta, "fd": body.fail_delta, "id": body.task_id},
            )
        kd = max(0, int(body.keyword_delta or 0))
        if kd:
            cur.execute(
                """
                UPDATE SJZQ_DEVICE
                   SET KEYWORD_RUN_COUNT = NVL(KEYWORD_RUN_COUNT, 0) + :kd,
                       UPDATE_TIME = SYSTIMESTAMP
                 WHERE DEVICE_ID = :id
                """,
                {"kd": kd, "id": device["device_id"]},
            )
        append_task_log(
            cur,
            body.task_id,
            body.message,
            device_id=device["device_id"],
            level=body.level,
        )
        notify_sync(
            "task_log",
            {
                "task_id": body.task_id,
                "device_id": device["device_id"],
                "message": body.message,
                "level": body.level,
            },
        )
        return ApiOk()


@router.post("/finish")
def task_finish(body: TaskFinishIn):
    finish_payload = {
        "task_id": body.task_id,
        "status": body.status,
        "error_msg": body.error_msg,
        "expected_product_count": body.expected_product_count,
        "expected_image_count": body.expected_image_count,
    }
    finish_sha256 = hashlib.sha256(
        json.dumps(finish_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    with get_conn() as conn:
        cur = conn.cursor()
        device = get_device_by_key(cur, body.device_key)
        if not device:
            return ApiOk(ok=False, message="device not registered")
        if body.finish_id:
            cur.execute(
                """
                SELECT PAYLOAD_SHA256, STATUS, RESULT_JSON, DEVICE_ID
                  FROM SJZQ_UPLOAD_RECEIPT WHERE IDEMPOTENCY_KEY=:key
                """,
                {"key": body.finish_id},
            )
            receipt = cur.fetchone()
            if receipt:
                result_raw = receipt[2].read() if hasattr(receipt[2], "read") else receipt[2]
                if int(receipt[3]) != int(device["device_id"]):
                    return ApiOk(ok=False, message="receipt device mismatch", data={"error_code": "DEVICE_MISMATCH"})
                if str(receipt[0]) != finish_sha256:
                    return ApiOk(ok=False, message="idempotency key payload conflict", data={"error_code": "IDEMPOTENCY_CONFLICT"})
                result = json.loads(result_raw) if result_raw else {}
                return ApiOk(message="already finished", data={**result, "acknowledged": True, "idempotent": True})
        if _has_collection_jobs(cur, body.task_id):
            return ApiOk(
                ok=False,
                message="Phase 2 Tasks finish only through confirmed Job aggregation",
                data={"error_code": "JOB_AGGREGATION_REQUIRED"},
            )
        requested = (body.status or "").strip().lower()
        if requested == "done":  # deprecated Android compatibility
            requested = "complete"
        if requested not in {"complete", "failed", "cancelled", "timed_out"}:
            return ApiOk(ok=False, message=f"invalid task completion status: {requested}",
                         data={"error_code": "INVALID_TASK_STATUS"})
        try:
            lock_device(cur, int(device["device_id"]))
            require_running_task(cur, body.task_id, device["device_id"], for_update=True)
            if requested == "complete":
                if body.finish_id:
                    if body.expected_product_count is None or body.expected_image_count is None:
                        return ApiOk(
                            ok=False,
                            message="finish manifest required",
                            data={"error_code": "FINISH_MANIFEST_REQUIRED"},
                        )
                    cur.execute(
                        """
                        SELECT
                          SUM(CASE WHEN OP_TYPE='product' AND STATUS='acked' THEN 1 ELSE 0 END),
                          SUM(CASE WHEN OP_TYPE='image' AND STATUS='acked' THEN 1 ELSE 0 END)
                        FROM SJZQ_UPLOAD_RECEIPT
                        WHERE TASK_ID=:tid AND DEVICE_ID=:did
                        """,
                        {"tid": body.task_id, "did": device["device_id"]},
                    )
                    confirmed = cur.fetchone() or (0, 0)
                    confirmed_products = int(confirmed[0] or 0)
                    confirmed_images = int(confirmed[1] or 0)
                    if (
                        confirmed_products != int(body.expected_product_count)
                        or confirmed_images != int(body.expected_image_count)
                    ):
                        return ApiOk(
                            ok=False,
                            message="finish manifest is not fully acknowledged",
                            data={
                                "error_code": "FINISH_INCOMPLETE",
                                "expected_product_count": body.expected_product_count,
                                "confirmed_product_count": confirmed_products,
                                "expected_image_count": body.expected_image_count,
                                "confirmed_image_count": confirmed_images,
                            },
                        )
                close_unfinished_items(cur, body.task_id, TaskItemStatus.FAILED,
                                       (body.error_msg or "任务结束，未采集到匹配商品")[:1000])
                status = completed_result(cur, body.task_id)
            else:
                status = TaskStatus(requested)
        except StateConflict as exc:
            if body.finish_id:
                cur.execute(
                    """
                    SELECT PAYLOAD_SHA256, STATUS, RESULT_JSON, DEVICE_ID
                      FROM SJZQ_UPLOAD_RECEIPT WHERE IDEMPOTENCY_KEY=:key
                    """,
                    {"key": body.finish_id},
                )
                concurrent_receipt = cur.fetchone()
                if concurrent_receipt and int(concurrent_receipt[3]) == int(device["device_id"]) \
                        and str(concurrent_receipt[0]) == finish_sha256:
                    result_raw = concurrent_receipt[2].read() if hasattr(concurrent_receipt[2], "read") else concurrent_receipt[2]
                    result = json.loads(result_raw) if result_raw else {}
                    return ApiOk(message="already finished", data={**result, "acknowledged": True, "idempotent": True})
            # A repeated finish with the same resulting terminal state is idempotent.
            try:
                terminal_task = get_task_state(cur, body.task_id)
                if terminal_task["device_id"] != int(device["device_id"]):
                    raise StateConflict("TASK_DEVICE_MISMATCH", str(terminal_task["device_id"]),
                                        str(device["device_id"]))
                current = task_status(terminal_task["status"])
                repeated = (
                    (requested != "complete" and current.value == requested)
                    or (requested == "complete" and current in {
                        TaskStatus.SUCCEEDED, TaskStatus.PARTIALLY_SUCCEEDED
                    })
                )
            except (StateConflict, ValueError):
                repeated = False
            if repeated:
                return ApiOk(message="already finished", data={"status": current.value, "idempotent": True})
            return ApiOk(ok=False, message=str(exc), data=state_error_data(exc))
        terminal_item_status = TaskItemStatus.CANCELLED if status in {TaskStatus.CANCELLED, TaskStatus.TIMED_OUT} else TaskItemStatus.FAILED
        terminal_item_message = (
            "任务已取消，条目未完成"
            if status == TaskStatus.CANCELLED
            else ((body.error_msg or "任务结束，未采集到匹配商品")[:1000])
        )
        close_unfinished_items(cur, body.task_id, terminal_item_status, terminal_item_message)
        try:
            transition_task(cur, body.task_id, status)
        except StateConflict as exc:
            return ApiOk(ok=False, message=str(exc), data=state_error_data(exc))
        cur.execute("UPDATE SJZQ_TASK SET ERROR_MSG=:err, END_TIME=SYSTIMESTAMP WHERE TASK_ID=:id",
                    {"err": (body.error_msg or "")[:1000] or None, "id": body.task_id})
        if REST_LOGIC_ENABLED:
            cur.execute(
                """
                UPDATE SJZQ_DEVICE
                   SET CURRENT_TASK_ID=NULL, STATUS='online', RUN_STATE='resting', RUN_STARTED_AT=NULL,
                       REST_UNTIL=SYSTIMESTAMP+NUMTODSINTERVAL(NVL(MIN_REST_MIN,30), 'MINUTE'), UPDATE_TIME=SYSTIMESTAMP
                 WHERE DEVICE_ID=:did AND CURRENT_TASK_ID=:task_id
                """,
                {"did": device["device_id"], "task_id": body.task_id},
            )
        else:
            cur.execute(
                """
                UPDATE SJZQ_DEVICE
                   SET CURRENT_TASK_ID=NULL, STATUS='online', RUN_STATE='idle', RUN_STARTED_AT=NULL,
                       REST_UNTIL=NULL, UPDATE_TIME=SYSTIMESTAMP
                 WHERE DEVICE_ID=:did AND CURRENT_TASK_ID=:task_id
                """,
                {"did": device["device_id"], "task_id": body.task_id},
            )
        # Excel 准字+规格任务以明细 done/failed 为准；普通多商品采集保留原商品成功计数。
        cur.execute(
            """
            UPDATE SJZQ_TASK t
               SET SUCCESS_COUNT = (
                       SELECT COUNT(*) FROM SJZQ_TASK_ITEM i
                         WHERE i.TASK_ID = t.TASK_ID AND i.STATUS IN ('succeeded','done')
                   ),
                   FAIL_COUNT = (
                       SELECT COUNT(*) FROM SJZQ_TASK_ITEM i
                         WHERE i.TASK_ID = t.TASK_ID AND i.STATUS IN ('failed','not_matched')
                   )
             WHERE t.TASK_ID = :task_id
               AND EXISTS (
                   SELECT 1 FROM SJZQ_TASK_ITEM i
                    WHERE i.TASK_ID = t.TASK_ID
                      AND i.TARGET_APPROVAL IS NOT NULL
                      AND i.TARGET_SPEC IS NOT NULL
               )
            """,
            {"task_id": body.task_id},
        )
        append_task_log(
            cur,
            body.task_id,
            f"任务结束 status={status.value}",
            device_id=device["device_id"],
        )
        result = {
            "task_id": body.task_id,
            "status": status.value,
            "acknowledged": True,
            "idempotent": False,
            "confirmed_product_count": body.expected_product_count,
            "confirmed_image_count": body.expected_image_count,
        }
        if body.finish_id:
            cur.execute(
                """
                INSERT INTO SJZQ_UPLOAD_RECEIPT (
                    IDEMPOTENCY_KEY, TASK_ID, DEVICE_ID, OP_TYPE, PAYLOAD_SHA256,
                    RESULT_JSON, STATUS
                ) VALUES (:key, :tid, :did, 'finish', :sha, :result_json, 'acked')
                """,
                {
                    "key": body.finish_id,
                    "tid": body.task_id,
                    "did": device["device_id"],
                    "sha": finish_sha256,
                    "result_json": json.dumps(result, ensure_ascii=False, sort_keys=True),
                },
            )
        return ApiOk(data=result)


def get_task_state_for_finish(cur, task_id: int) -> str:
    cur.execute("SELECT STATUS FROM SJZQ_TASK WHERE TASK_ID=:id", {"id": task_id})
    row = cur.fetchone()
    if not row:
        raise StateConflict("TASK_NOT_FOUND", "missing", "finish")
    return str(row[0]).lower()


def _add_task_capabilities(task: dict) -> None:
    try:
        status = task_status(str(task.get("status") or ""))
    except ValueError:
        task.update(terminal=False, dispatchable=False, can_cancel=False, can_retry=False)
        return
    task["terminal"] = status in {TaskStatus.SUCCEEDED, TaskStatus.PARTIALLY_SUCCEEDED,
                                  TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.TIMED_OUT}
    task["dispatchable"] = status == TaskStatus.PENDING and task.get("review_status") == "approved"
    task["can_cancel"] = status in {TaskStatus.PENDING, TaskStatus.RUNNING}
    task["can_retry"] = status in {TaskStatus.PARTIALLY_SUCCEEDED, TaskStatus.FAILED,
                                    TaskStatus.CANCELLED, TaskStatus.TIMED_OUT}
