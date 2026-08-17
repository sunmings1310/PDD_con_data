"""投屏：Web 发起请求，App MediaProjection 采帧，经 WebSocket 中继。"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from server.auth_util import decode_token, require_perms
from server.cast_state import cast_state
from server.db import get_conn, row_as_dict
from server.schemas import ApiOk
from server.tenant import require_tenant_perms
from server.services import get_device_by_key

router = APIRouter(tags=["cast"])


def _load_device(device_id: int, tenant=None) -> dict | None:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT DEVICE_ID, DEVICE_KEY, DEVICE_NAME, STATUS
              FROM SJZQ_DEVICE WHERE DEVICE_ID = :id AND REVOKED_AT IS NULL
                AND (:enterprise_id IS NULL OR (ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id))
            """,
            {"id": device_id, "enterprise_id": tenant.enterprise_id if tenant else None,
             "workspace_id": tenant.workspace_id if tenant else None},
        )
        return row_as_dict(cur)


@router.post("/api/cast/{device_id}/start")
async def cast_start(device_id: int, tenant=Depends(require_tenant_perms("device:cast"))):
    d = _load_device(device_id, tenant)
    if not d:
        return ApiOk(ok=False, message="设备不存在")
    cast_state.request_cast(int(d["device_id"]), d["device_key"])
    return ApiOk(message="已向设备发起投屏请求，等待 APP 自动授权并推流")


@router.post("/api/cast/{device_id}/stop")
async def cast_stop(device_id: int, tenant=Depends(require_tenant_perms("device:cast"))):
    if not _load_device(device_id, tenant):
        return ApiOk(ok=False, message="设备不存在")
    cast_state.stop_cast(device_id)
    room = cast_state.rooms_by_id.get(device_id)
    if room:
        # 通知 App 停止
        if room.publisher:
            try:
                await room.publisher.send_text(json.dumps({"type": "stop"}))
            except Exception:
                pass
        dead = []
        for v in list(room.viewers):
            try:
                await v.send_text(json.dumps({"type": "stopped"}))
            except Exception:
                dead.append(v)
        for v in dead:
            room.viewers.discard(v)
    return ApiOk(message="已停止投屏")


@router.get("/api/cast/{device_id}/status")
def cast_status(device_id: int, tenant=Depends(require_tenant_perms("device:view"))):
    if not _load_device(device_id, tenant):
        return ApiOk(ok=False, message="设备不存在")
    room = cast_state.rooms_by_id.get(device_id)
    return ApiOk(
        data={
            "requested": bool(room and room.requested),
            "publishing": bool(room and room.publisher is not None),
            "viewers": len(room.viewers) if room else 0,
        }
    )


@router.websocket("/ws/cast/pub/{device_key}")
async def cast_publish(ws: WebSocket, device_key: str):
    await ws.accept()
    # 解析设备
    with get_conn() as conn:
        cur = conn.cursor()
        row = get_device_by_key(cur, device_key)
    if not row:
        await ws.send_text(json.dumps({"type": "error", "message": "unknown device"}))
        await ws.close()
        return

    device_id = int(row["device_id"])
    room = cast_state.ensure_room(device_id, device_key)
    room.publisher = ws
    room.requested = True
    try:
        await ws.send_text(json.dumps({"type": "ready", "device_id": device_id}))
        while True:
            message = await ws.receive()
            if message.get("type") == "websocket.disconnect":
                break
            data = message.get("bytes")
            if data:
                room.last_frame = data
                dead = []
                for v in list(room.viewers):
                    try:
                        await v.send_bytes(data)
                    except Exception:
                        dead.append(v)
                for v in dead:
                    room.viewers.discard(v)
                continue
            text = message.get("text")
            if text:
                try:
                    obj = json.loads(text)
                except Exception:
                    continue
                if obj.get("type") == "ping":
                    await ws.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        pass
    finally:
        if room.publisher is ws:
            room.publisher = None
        # 无 viewer 时允许保持 requested=false
        if not room.viewers:
            room.requested = False


@router.websocket("/ws/cast/view/{device_id}")
async def cast_view(ws: WebSocket, device_id: int):
    await ws.accept()
    try:
        payload = decode_token(ws.query_params.get("token") or "")
        enterprise_id = int(ws.query_params.get("enterprise_id") or 0)
        workspace_id = int(ws.query_params.get("workspace_id") or 0)
    except Exception:
        await ws.send_text(json.dumps({"type": "error", "message": "unauthorized"}))
        await ws.close(code=1008)
        return
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT COUNT(*) FROM SJZQ_ENTERPRISE_MEMBERSHIP m
                         JOIN SJZQ_USER u ON u.USER_ID=m.USER_ID AND u.STATUS='enabled'
                         JOIN SJZQ_WORKSPACE w ON w.ENTERPRISE_ID=m.ENTERPRISE_ID
                         JOIN SJZQ_ROLE_PERM rp ON rp.ROLE_ID=m.ROLE_ID AND rp.PERM_CODE='device:cast'
                        WHERE m.USER_ID=:user_id AND m.ENTERPRISE_ID=:enterprise_id
                          AND m.STATUS='active' AND w.WORKSPACE_ID=:workspace_id AND w.STATUS='active'
                          AND (NOT EXISTS (SELECT 1 FROM SJZQ_WORKSPACE_MEMBERSHIP x
                                          WHERE x.WORKSPACE_ID=w.WORKSPACE_ID)
                               OR EXISTS (SELECT 1 FROM SJZQ_WORKSPACE_MEMBERSHIP x
                                           WHERE x.ENTERPRISE_ID=m.ENTERPRISE_ID
                                             AND x.WORKSPACE_ID=w.WORKSPACE_ID AND x.USER_ID=m.USER_ID))""",
                    {"user_id": int(payload["uid"]), "enterprise_id": enterprise_id,
                     "workspace_id": workspace_id})
        allowed = int(cur.fetchone()[0] or 0) > 0
    if not allowed:
        await ws.send_text(json.dumps({"type": "error", "message": "unauthorized"}))
        await ws.close(code=1008)
        return
    scope = type("Scope", (), {"enterprise_id": enterprise_id, "workspace_id": workspace_id})()
    d = _load_device(device_id, scope)
    if not d:
        await ws.send_text(json.dumps({"type": "error", "message": "device not found"}))
        await ws.close()
        return
    room = cast_state.ensure_room(int(d["device_id"]), d["device_key"])
    room.viewers.add(ws)
    room.requested = True
    try:
        await ws.send_text(
            json.dumps(
                {
                    "type": "hello",
                    "device_id": device_id,
                    "publishing": room.publisher is not None,
                }
            )
        )
        if room.last_frame:
            await ws.send_bytes(room.last_frame)
        while True:
            msg = await ws.receive_text()
            if msg == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        pass
    finally:
        room.viewers.discard(ws)
        if not room.viewers and room.publisher is None:
            room.requested = False
