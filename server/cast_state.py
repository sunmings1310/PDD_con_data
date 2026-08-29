"""投屏与设备指令的内存状态（进程内）。"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket


@dataclass
class DeviceCastRoom:
    device_id: int
    device_key: str
    requested: bool = False
    publisher: WebSocket | None = None
    viewers: set[WebSocket] = field(default_factory=set)
    last_frame: bytes | None = None


class CastState:
    def __init__(self) -> None:
        self.rooms_by_id: dict[int, DeviceCastRoom] = {}
        self.key_to_id: dict[str, int] = {}
        self.abort_flags: dict[int, bool] = {}
        self.lock = asyncio.Lock()
        # 一键更新：待下发的 APK 指令（按 device_key 保留，ack 后清除）
        self.apk_meta: dict[str, Any] = {}
        self.pending_apk: dict[str, Any] | None = None
        self.apk_pending_keys: set[str] = set()
        self.pending_apk_by_scope: dict[tuple[int, int], dict[str, Any]] = {}
        self.apk_keys_by_scope: dict[tuple[int, int], set[str]] = {}
        self.apk_generation_by_scope: dict[tuple[int, int], int] = {}
        self.apk_lock = threading.RLock()

    def ensure_room(self, device_id: int, device_key: str) -> DeviceCastRoom:
        room = self.rooms_by_id.get(device_id)
        if room is None:
            room = DeviceCastRoom(device_id=device_id, device_key=device_key)
            self.rooms_by_id[device_id] = room
        room.device_key = device_key
        self.key_to_id[device_key] = device_id
        return room

    def request_cast(self, device_id: int, device_key: str) -> None:
        room = self.ensure_room(device_id, device_key)
        room.requested = True

    def stop_cast(self, device_id: int) -> None:
        room = self.rooms_by_id.get(device_id)
        if room:
            room.requested = False

    async def disconnect_room(self, device_id: int, reason: str) -> None:
        room = self.rooms_by_id.pop(device_id, None)
        if not room:
            return
        self.key_to_id.pop(room.device_key, None)
        peers = ([room.publisher] if room.publisher else []) + list(room.viewers)
        room.publisher = None
        room.viewers.clear()
        room.requested = False
        for peer in peers:
            try:
                await peer.send_text('{"type":"error","message":"' + reason + '"}')
                await peer.close(code=1008)
            except Exception:
                pass

    def cast_requested_for_key(self, device_key: str) -> bool:
        did = self.key_to_id.get(device_key)
        if did is None:
            return False
        room = self.rooms_by_id.get(did)
        return bool(room and room.requested)

    def set_abort(self, device_id: int, value: bool = True) -> None:
        self.abort_flags[device_id] = value

    def pop_abort_for_key(self, device_key: str) -> bool:
        did = self.key_to_id.get(device_key)
        if did is None:
            return False
        return bool(self.abort_flags.pop(did, False))

    def device_commands(self, device_key: str) -> dict[str, Any]:
        with self.apk_lock:
            cmds: dict[str, Any] = {
                "cast_request": self.cast_requested_for_key(device_key),
                "abort_task": self.pop_abort_for_key(device_key),
                "update_apk": None,
            }
            for scope, payload in tuple(self.pending_apk_by_scope.items()):
                if device_key in self.apk_keys_by_scope.get(scope, set()):
                    cmds["update_apk"] = dict(payload)
                    break
            return cmds

    def set_apk_meta(self, version_name: str, version_code: int, size: str | int) -> None:
        self.apk_meta = {
            "version_name": version_name,
            "version_code": int(version_code or 0),
            "size": int(size or 0),
        }

    def get_pending_apk(self, scope: tuple[int, int] = (1, 1)) -> dict[str, Any] | None:
        with self.apk_lock:
            pending = self.pending_apk_by_scope.get(scope)
            if not pending:
                return None
            return {**pending, "pending_devices": len(self.apk_keys_by_scope.get(scope, set()))}

    def push_apk_update(self, payload: dict[str, Any], device_keys: list[str],
                        scope: tuple[int, int] = (1, 1)) -> None:
        with self.apk_lock:
            generation = self.apk_generation_by_scope.get(scope, 0) + 1
            self.apk_generation_by_scope[scope] = generation
            payload = {**payload, "generation": generation}
            self.pending_apk = dict(payload)
            self.apk_pending_keys = {k for k in device_keys if k}
            self.pending_apk_by_scope[scope] = dict(payload)
            self.apk_keys_by_scope[scope] = {k for k in device_keys if k}
        self.set_apk_meta(
            str(payload.get("version_name") or ""),
            int(payload.get("version_code") or 0),
            payload.get("size") or 0,
        )

    def ack_apk_update(self, device_key: str, version_name: str = "",
                       scope: tuple[int, int] | None = None) -> None:
        """Legacy delivery notification; it deliberately does not claim installation."""
        # Android's system Package Installer completes outside the app process. A
        # download/start acknowledgement is therefore not evidence that the APK is
        # installed; keep the command until the new app version heartbeats.
        return None

    def confirm_apk_install(self, device_key: str, version_name: str, generation: int,
                            scope: tuple[int, int]) -> bool:
        """Consume a pending OTA command only after the installed app heartbeats."""
        with self.apk_lock:
            expected = self.pending_apk_by_scope.get(scope)
            if (not expected or str(expected.get("version_name") or "") != version_name
                    or int(expected.get("generation") or 0) != generation):
                return False
            keys = self.apk_keys_by_scope.get(scope, set())
            if device_key not in keys:
                return False
            keys.discard(device_key)
            self.apk_pending_keys.discard(device_key)
            if not keys:
                self.pending_apk_by_scope.pop(scope, None)
            if not self.apk_pending_keys:
                self.pending_apk = None
            return True


cast_state = CastState()
