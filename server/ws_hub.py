"""简易 WebSocket 广播：设备日志 / 任务进度。"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["ws"])


class Hub:
    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()
        self.lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self.lock:
            self.clients.add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self.lock:
            self.clients.discard(ws)

    async def broadcast(self, event: str, data: Any) -> None:
        payload = json.dumps({"event": event, "data": data}, ensure_ascii=False, default=str)
        dead: list[WebSocket] = []
        async with self.lock:
            peers = list(self.clients)
        for ws in peers:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)


hub = Hub()


@router.websocket("/ws/realtime")
async def realtime(ws: WebSocket):
    await hub.connect(ws)
    try:
        while True:
            # 心跳保活；客户端可发 ping
            msg = await ws.receive_text()
            if msg == "ping":
                await ws.send_text(json.dumps({"event": "pong"}))
    except WebSocketDisconnect:
        await hub.disconnect(ws)
    except Exception:
        await hub.disconnect(ws)


def notify_sync(event: str, data: Any) -> None:
    """从同步路由里尽力推送。"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(hub.broadcast(event, data))
    except Exception:
        pass
