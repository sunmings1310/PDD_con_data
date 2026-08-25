"""Tenant- and device-scoped realtime task log delivery."""

from __future__ import annotations

import asyncio
from concurrent.futures import Future
from dataclasses import dataclass
import json
import logging
from threading import Lock
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from server.auth_util import decode_token
from server.db import get_conn

router = APIRouter(tags=["ws"])
logger = logging.getLogger("sjzq.realtime_ws")

AUTH_TIMEOUT_SECONDS = 5.0
SEND_TIMEOUT_SECONDS = 3.0


@dataclass(frozen=True)
class RealtimeChannel:
    """A server-derived delivery boundary; never populated from client tenant data."""

    enterprise_id: int
    workspace_id: int
    device_id: int


class RealtimeAuthError(Exception):
    """Deliberately non-specific so resource existence is not disclosed."""


def resolve_realtime_channel(cur: Any, user_id: int, device_id: int) -> RealtimeChannel | None:
    """Resolve an authorized channel from identity and the authoritative Device row."""
    cur.execute(
        """
        SELECT d.ENTERPRISE_ID, d.WORKSPACE_ID, d.DEVICE_ID
          FROM SJZQ_DEVICE d
          JOIN SJZQ_USER u
            ON u.USER_ID = :user_id AND u.STATUS = 'enabled'
          JOIN SJZQ_ENTERPRISE_MEMBERSHIP em
            ON em.USER_ID = u.USER_ID
           AND em.ENTERPRISE_ID = d.ENTERPRISE_ID
           AND em.STATUS = 'active'
          JOIN SJZQ_ROLE_PERM rp
            ON rp.ROLE_ID = em.ROLE_ID AND rp.PERM_CODE = 'device:view'
          JOIN SJZQ_ENTERPRISE e
            ON e.ENTERPRISE_ID = d.ENTERPRISE_ID AND e.STATUS = 'active'
          JOIN SJZQ_WORKSPACE w
            ON w.WORKSPACE_ID = d.WORKSPACE_ID
           AND w.ENTERPRISE_ID = d.ENTERPRISE_ID
           AND w.STATUS = 'active'
         WHERE d.DEVICE_ID = :device_id
           AND d.REVOKED_AT IS NULL
           AND (
                 NOT EXISTS (
                   SELECT 1 FROM SJZQ_WORKSPACE_MEMBERSHIP wx
                    WHERE wx.WORKSPACE_ID = d.WORKSPACE_ID
                 )
                 OR EXISTS (
                   SELECT 1 FROM SJZQ_WORKSPACE_MEMBERSHIP wm
                    WHERE wm.ENTERPRISE_ID = d.ENTERPRISE_ID
                      AND wm.WORKSPACE_ID = d.WORKSPACE_ID
                      AND wm.USER_ID = u.USER_ID
                 )
               )
        """,
        {"user_id": int(user_id), "device_id": int(device_id)},
    )
    row = cur.fetchone()
    if row is None:
        return None
    return RealtimeChannel(int(row[0]), int(row[1]), int(row[2]))


def resolve_task_event_channel(cur: Any, task_id: int, device_id: int) -> RealtimeChannel | None:
    """Derive producer scope from Task/Device ownership and assignment."""
    cur.execute(
        """
        SELECT t.ENTERPRISE_ID, t.WORKSPACE_ID, d.DEVICE_ID
          FROM SJZQ_TASK t
          JOIN SJZQ_DEVICE d
            ON d.DEVICE_ID = :device_id
           AND d.ENTERPRISE_ID = t.ENTERPRISE_ID
           AND d.WORKSPACE_ID = t.WORKSPACE_ID
           AND d.REVOKED_AT IS NULL
         WHERE t.TASK_ID = :task_id
           AND t.DEVICE_ID = d.DEVICE_ID
        """,
        {"task_id": int(task_id), "device_id": int(device_id)},
    )
    row = cur.fetchone()
    if row is None:
        return None
    return RealtimeChannel(int(row[0]), int(row[1]), int(row[2]))


def authorize_realtime(token: str, device_id: int) -> RealtimeChannel:
    """Authenticate a socket and resolve its only authorized resource channel."""
    try:
        payload = decode_token(token)
        user_id = int(payload["uid"])
        with get_conn() as conn:
            channel = resolve_realtime_channel(conn.cursor(), user_id, int(device_id))
    except (HTTPException, KeyError, TypeError, ValueError) as exc:
        raise RealtimeAuthError from exc
    if channel is None:
        raise RealtimeAuthError
    return channel


class Hub:
    def __init__(self) -> None:
        self.clients: dict[RealtimeChannel, set[WebSocket]] = {}
        self.lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._state_lock = Lock()
        self._stats = {
            "scheduled": 0,
            "schedule_failures": 0,
            "delivery_failures": 0,
        }

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        with self._state_lock:
            self._loop = loop

    def unbind_loop(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        with self._state_lock:
            if loop is None or self._loop is loop:
                self._loop = None

    def _increment(self, key: str) -> None:
        with self._state_lock:
            self._stats[key] += 1

    def stats(self) -> dict[str, int]:
        with self._state_lock:
            return dict(self._stats)

    async def connect(self, ws: WebSocket, channel: RealtimeChannel) -> None:
        async with self.lock:
            self.clients.setdefault(channel, set()).add(ws)

    async def disconnect(self, ws: WebSocket, channel: RealtimeChannel) -> None:
        async with self.lock:
            peers = self.clients.get(channel)
            if peers is None:
                return
            peers.discard(ws)
            if not peers:
                self.clients.pop(channel, None)

    async def broadcast(self, channel: RealtimeChannel, event: str, data: Any) -> None:
        payload = json.dumps({"event": event, "data": data}, ensure_ascii=False, default=str)
        async with self.lock:
            peers = list(self.clients.get(channel, ()))
        dead: list[WebSocket] = []
        for ws in peers:
            try:
                await asyncio.wait_for(ws.send_text(payload), timeout=SEND_TIMEOUT_SECONDS)
            except Exception:  # network/send timeout is isolated to this peer
                self._increment("delivery_failures")
                logger.exception(
                    "realtime delivery failed enterprise=%s workspace=%s device=%s",
                    channel.enterprise_id,
                    channel.workspace_id,
                    channel.device_id,
                )
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws, channel)

    def schedule(self, channel: RealtimeChannel, event: str, data: Any) -> bool:
        with self._state_lock:
            loop = self._loop
        if loop is None or loop.is_closed() or not loop.is_running():
            self._increment("schedule_failures")
            logger.error(
                "realtime scheduling rejected: app loop unavailable enterprise=%s workspace=%s device=%s",
                channel.enterprise_id,
                channel.workspace_id,
                channel.device_id,
            )
            return False
        try:
            future = asyncio.run_coroutine_threadsafe(self.broadcast(channel, event, data), loop)
            future.add_done_callback(self._observe_delivery)
            self._increment("scheduled")
            return True
        except Exception:
            self._increment("schedule_failures")
            logger.exception(
                "realtime scheduling failed enterprise=%s workspace=%s device=%s",
                channel.enterprise_id,
                channel.workspace_id,
                channel.device_id,
            )
            return False

    def _observe_delivery(self, future: Future[None]) -> None:
        try:
            future.result()
        except Exception:
            self._increment("schedule_failures")
            logger.exception("realtime scheduled delivery crashed")


hub = Hub()


async def _reject(ws: WebSocket) -> None:
    logger.warning("realtime websocket authorization rejected")
    await ws.close(code=1008, reason="authorization failed")


@router.websocket("/ws/realtime")
async def realtime(ws: WebSocket) -> None:
    await ws.accept()
    channel: RealtimeChannel | None = None
    try:
        raw = await asyncio.wait_for(ws.receive_text(), timeout=AUTH_TIMEOUT_SECONDS)
        auth = json.loads(raw)
        if not isinstance(auth, dict) or auth.get("type") != "auth":
            raise RealtimeAuthError
        token = auth.get("token")
        device_id = auth.get("device_id")
        if not isinstance(token, str) or not token or isinstance(device_id, bool):
            raise RealtimeAuthError
        channel = await asyncio.to_thread(authorize_realtime, token, int(device_id))
        await hub.connect(ws, channel)
        await ws.send_text(json.dumps({"event": "ready", "data": {"device_id": channel.device_id}}))
        while True:
            msg = await ws.receive_text()
            if msg == "ping":
                await ws.send_text(json.dumps({"event": "pong"}))
    except (RealtimeAuthError, asyncio.TimeoutError, json.JSONDecodeError, TypeError, ValueError):
        await _reject(ws)
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("realtime websocket failed after handshake")
    finally:
        if channel is not None:
            await hub.disconnect(ws, channel)


def notify_sync(channel: RealtimeChannel, event: str, data: Any) -> bool:
    """Schedule delivery on the FastAPI app loop and return an observable result."""
    return hub.schedule(channel, event, data)
