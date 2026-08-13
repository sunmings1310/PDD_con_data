"""App 一键更新：上传 APK、停任务、心跳下发更新指令。"""

from __future__ import annotations

import re
import shutil

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from pydantic import BaseModel

from server.auth_util import require_perms, write_op_log
from server.cast_state import cast_state
from server.db import get_conn, rows_as_dicts
from server.ota_meta import apk_dir, latest_payload, save_meta
from server.schemas import ApiOk
from server.task_state import StateConflict, TaskItemStatus, TaskStatus
from server.task_state_service import close_unfinished_items, transition_task

router = APIRouter(prefix="/api/ota", tags=["ota"])


class OtaAckIn(BaseModel):
    device_key: str
    version_name: str = ""


class OtaPushIn(BaseModel):
    version_name: str | None = None
    version_code: int = 0


def _apk_dir():
    return apk_dir()


@router.get("/latest")
def ota_latest():
    """App 无鉴权查询服务端最新 APK 版本（用于手工同步 / 顶部更新条）。"""
    return ApiOk(data=latest_payload())


@router.get("/status")
def ota_status(_=Depends(require_perms("system:config"))):
    pending = cast_state.get_pending_apk()
    latest = latest_payload()
    return ApiOk(
        data={
            "pending": pending,
            "has_apk": latest["has_apk"],
            "apk_size": latest["size"],
            "apk_url": latest["apk_url"],
            "meta": {
                "version_name": latest["version_name"],
                "version_code": latest["version_code"],
                "size": latest["size"],
            },
        }
    )


@router.post("/upload")
async def upload_apk(
    request: Request,
    file: UploadFile = File(...),
    version_name: str = Form("1.0.0"),
    version_code: int = Form(0),
    user=Depends(require_perms("system:config")),
):
    name = (file.filename or "app.apk").lower()
    if not name.endswith(".apk"):
        return ApiOk(ok=False, message="请上传 .apk 文件")
    dest = _apk_dir() / "latest.apk"
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    ver = (version_name or "1.0.0").strip()[:32]
    if ver in ("1.0.0", "") and file.filename:
        m = re.search(r"v?(\d+\.\d+\.\d+)", file.filename)
        if m:
            ver = m.group(1)
    save_meta(ver, int(version_code or 0), dest.stat().st_size)
    with get_conn() as conn:
        cur = conn.cursor()
        write_op_log(
            cur,
            user_id=user["user_id"],
            username=user["username"],
            action="ota_upload",
            module="ota",
            detail=f"上传APK {ver} size={dest.stat().st_size}",
            ip=request.client.host if request.client else None,
        )
    payload = latest_payload()
    return ApiOk(
        message="uploaded",
        data={
            "version_name": ver,
            "version_code": int(version_code or 0),
            "size": dest.stat().st_size,
            "apk_url": payload.get("apk_url") or "/media/apk/latest.apk",
        },
    )


@router.post("/push")
def push_update(
    request: Request,
    body: OtaPushIn | None = None,
    user=Depends(require_perms("system:config")),
):
    """停止所有设备进行中任务，并向全部设备下发更新指令。"""
    apk = _apk_dir() / "latest.apk"
    if not apk.is_file():
        return ApiOk(ok=False, message="请先上传 APK")

    body = body or OtaPushIn()
    meta = cast_state.apk_meta or {}
    ver = (body.version_name or meta.get("version_name") or "1.0.0").strip()[:32]
    code = int(body.version_code or meta.get("version_code") or 0)

    aborted = 0
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT DEVICE_ID, DEVICE_KEY, CURRENT_TASK_ID
              FROM SJZQ_DEVICE
             WHERE CURRENT_TASK_ID IS NOT NULL
            """
        )
        busy = rows_as_dicts(cur)
        for d in busy:
            tid = d.get("current_task_id")
            did = int(d["device_id"])
            if tid:
                try:
                    transition_task(cur, int(tid), TaskStatus.CANCELLED)
                    close_unfinished_items(cur, int(tid), TaskItemStatus.CANCELLED, "一键更新终止，条目未完成")
                    cur.execute("UPDATE SJZQ_TASK SET ERROR_MSG='一键更新终止', END_TIME=SYSTIMESTAMP WHERE TASK_ID=:id",
                                {"id": int(tid)})
                except StateConflict:
                    # Device occupancy is still conditionally cleared below; the task authority is not overwritten.
                    pass
            cur.execute(
                """
                UPDATE SJZQ_DEVICE
                   SET CURRENT_TASK_ID=NULL, STATUS='online', RUN_STATE='idle', RUN_STARTED_AT=NULL,
                       REST_UNTIL=NULL, UPDATE_TIME=SYSTIMESTAMP
                 WHERE DEVICE_ID=:id AND CURRENT_TASK_ID=:tid
                """,
                {"id": did, "tid": tid},
            )
            cast_state.set_abort(did, True)
            aborted += 1

        cur.execute("SELECT DEVICE_KEY FROM SJZQ_DEVICE")
        keys = [r["device_key"] for r in rows_as_dicts(cur) if r.get("device_key")]
        write_op_log(
            cur,
            user_id=user["user_id"],
            username=user["username"],
            action="ota_push",
            module="ota",
            detail=f"一键更新 v{ver} 设备={len(keys)} 停任务={aborted}",
            ip=request.client.host if request.client else None,
        )

    save_meta(ver, code, apk.stat().st_size)
    latest = latest_payload()
    payload = {
        "apk_url": latest.get("apk_url") or "/media/apk/latest.apk",
        "version_name": ver,
        "version_code": code,
        "size": apk.stat().st_size,
    }
    cast_state.push_apk_update(payload, device_keys=keys)
    return ApiOk(
        message="已下发更新",
        data={"devices": len(keys), "aborted_tasks": aborted, **payload},
    )


@router.post("/ack")
def ack_update(body: OtaAckIn):
    """App 开始下载/安装后确认。"""
    cast_state.ack_apk_update(body.device_key, body.version_name)
    return ApiOk(message="acked")
