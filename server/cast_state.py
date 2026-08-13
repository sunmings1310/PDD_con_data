"""投屏与设备指令的内存状态（进程内）。"""

from __future__ import annotations

import asyncio
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
        cmds: dict[str, Any] = {
            "cast_request": self.cast_requested_for_key(device_key),
            "abort_task": self.pop_abort_for_key(device_key),
            "update_apk": None,
        }
        if self.pending_apk and device_key in self.apk_pending_keys:
            cmds["update_apk"] = dict(self.pending_apk)
        return cmds

    def set_apk_meta(self, version_name: str, version_code: int, size: str | int) -> None:
        self.apk_meta = {
            "version_name": version_name,
            "version_code": int(version_code or 0),
            "size": int(size or 0),
        }

    def get_pending_apk(self) -> dict[str, Any] | None:
        if not self.pending_apk:
            return None
        return {
            **self.pending_apk,
            "pending_devices": len(self.apk_pending_keys),
        }

    def push_apk_update(self, payload: dict[str, Any], device_keys: list[str]) -> None:
        self.pending_apk = dict(payload)
        self.apk_pending_keys = {k for k in device_keys if k}
        self.set_apk_meta(
            str(payload.get("version_name") or ""),
            int(payload.get("version_code") or 0),
            payload.get("size") or 0,
        )

    def ack_apk_update(self, device_key: str, version_name: str = "") -> None:
        self.apk_pending_keys.discard(device_key)
        if not self.apk_pending_keys:
            # 全部 ack 后仍保留 meta，便于状态页展示；清空 pending 避免新设备误触发
            self.pending_apk = None


cast_state = CastState()
