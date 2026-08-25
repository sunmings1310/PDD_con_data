"""Offline contract tests for tenant-scoped realtime WebSocket delivery."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from fastapi import HTTPException, WebSocketDisconnect

for _key, _value in {
    "APP_ENV": "test",
    "ORACLE_HOST": "127.0.0.1",
    "ORACLE_PORT": "1521",
    "ORACLE_SERVICE": "TEST",
    "ORACLE_USER": "TEST",
    "ORACLE_PASSWORD": "test-password",
    "JWT_SECRET": "Test-only-JWT-secret-32-characters!",
}.items():
    os.environ.setdefault(_key, _value)

from server import ws_hub  # noqa: E402
from server.ws_hub import Hub, RealtimeAuthError, RealtimeChannel  # noqa: E402


class _Cursor:
    def __init__(self, row=None):
        self.row = row
        self.sql = ""
        self.binds = {}

    def execute(self, sql, binds):
        self.sql = sql
        self.binds = binds

    def fetchone(self):
        return self.row


class _Socket:
    def __init__(self, *, inbound=None, fail_send=False):
        self.inbound = list(inbound or [])
        self.fail_send = fail_send
        self.accepted = False
        self.sent: list[str] = []
        self.closed: tuple[int, str] | None = None
        self.delivered = asyncio.Event()

    async def accept(self):
        self.accepted = True

    async def receive_text(self):
        if not self.inbound:
            raise WebSocketDisconnect(code=1000)
        value = self.inbound.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    async def send_text(self, value):
        if self.fail_send:
            raise ConnectionError("test delivery failure")
        self.sent.append(value)
        self.delivered.set()

    async def close(self, code=1000, reason=""):
        self.closed = (code, reason)


class ResolverContractTests(unittest.TestCase):
    def test_authorized_resource_scope_is_derived_from_database(self):
        cur = _Cursor((11, 22, 33))
        result = ws_hub.resolve_realtime_channel(cur, user_id=7, device_id=33)
        self.assertEqual(RealtimeChannel(11, 22, 33), result)
        normalized = " ".join(cur.sql.split()).upper()
        self.assertIn("RP.PERM_CODE = 'DEVICE:VIEW'", normalized)
        self.assertIn("D.REVOKED_AT IS NULL", normalized)
        self.assertIn("SJZQ_ENTERPRISE_MEMBERSHIP", normalized)
        self.assertIn("SJZQ_WORKSPACE_MEMBERSHIP", normalized)
        self.assertEqual({"user_id": 7, "device_id": 33}, cur.binds)

    def test_unauthorized_matrix_returns_no_channel_without_disclosure(self):
        for case in (
            "insufficient_permission",
            "disabled_user",
            "cross_tenant_device",
            "revoked_device",
            "workspace_membership_mismatch",
            "missing_device",
        ):
            with self.subTest(case=case):
                self.assertIsNone(ws_hub.resolve_realtime_channel(_Cursor(None), 7, 33))

    def test_task_device_scope_requires_assignment_and_tenant_match(self):
        good = _Cursor((11, 22, 33))
        self.assertEqual(
            RealtimeChannel(11, 22, 33),
            ws_hub.resolve_task_event_channel(good, task_id=44, device_id=33),
        )
        normalized = " ".join(good.sql.split()).upper()
        self.assertIn("D.ENTERPRISE_ID = T.ENTERPRISE_ID", normalized)
        self.assertIn("D.WORKSPACE_ID = T.WORKSPACE_ID", normalized)
        self.assertIn("T.DEVICE_ID = D.DEVICE_ID", normalized)
        self.assertIn("D.REVOKED_AT IS NULL", normalized)
        for case in ("cross_tenant", "cross_workspace", "wrong_device", "revoked"):
            with self.subTest(case=case):
                self.assertIsNone(ws_hub.resolve_task_event_channel(_Cursor(None), 44, 33))

    def test_invalid_token_is_normalized_to_realtime_auth_error(self):
        with patch.object(ws_hub, "decode_token", side_effect=HTTPException(status_code=401)):
            with self.assertRaises(RealtimeAuthError):
                ws_hub.authorize_realtime("bad", 33)

    def test_client_auth_frame_contains_no_client_tenant_scope(self):
        source = Path("web/src/views/devices/DeviceLive.vue").read_text(encoding="utf-8")
        auth_block = source[source.index("ws.onopen"):source.index("ws.onmessage")]
        self.assertIn("token:", auth_block)
        self.assertIn("device_id:", auth_block)
        self.assertNotIn("enterprise", auth_block.lower())
        self.assertNotIn("workspace", auth_block.lower())
        self.assertIn("setInterval(load, 8000)", source)

    def test_notification_is_after_database_context_commit_boundary(self):
        source = Path("server/routers/tasks.py").read_text(encoding="utf-8")
        body = source[source.index("def task_progress"):source.index("@router.post(\"/finish\")")]
        self.assertIn("# Commit is complete before realtime notification", body)
        self.assertLess(body.index("append_task_log("), body.index("notify_sync("))
        notify_line = next(line for line in body.splitlines() if line.startswith("    notify_sync("))
        self.assertEqual("    notify_sync(", notify_line)


class HubIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_same_tenant_workspace_and_device_receives(self):
        hub = Hub()
        target = RealtimeChannel(1, 2, 3)
        same = _Socket()
        other_tenant = _Socket()
        other_workspace = _Socket()
        other_device = _Socket()
        await hub.connect(same, target)
        await hub.connect(other_tenant, RealtimeChannel(9, 2, 3))
        await hub.connect(other_workspace, RealtimeChannel(1, 9, 3))
        await hub.connect(other_device, RealtimeChannel(1, 2, 9))
        await hub.broadcast(target, "task_log", {"task_id": 4})
        self.assertEqual(1, len(same.sent))
        self.assertEqual([], other_tenant.sent)
        self.assertEqual([], other_workspace.sent)
        self.assertEqual([], other_device.sent)

    async def test_delivery_failure_is_counted_and_failed_peer_removed(self):
        hub = Hub()
        channel = RealtimeChannel(1, 2, 3)
        failed = _Socket(fail_send=True)
        await hub.connect(failed, channel)
        with self.assertLogs("sjzq.realtime_ws", level="ERROR"):
            await hub.broadcast(channel, "task_log", {})
        self.assertEqual(1, hub.stats()["delivery_failures"])
        self.assertNotIn(channel, hub.clients)

    async def test_worker_thread_schedules_on_bound_app_loop(self):
        hub = Hub()
        channel = RealtimeChannel(1, 2, 3)
        socket = _Socket()
        await hub.connect(socket, channel)
        hub.bind_loop(asyncio.get_running_loop())
        scheduled = await asyncio.to_thread(hub.schedule, channel, "task_log", {"task_id": 4})
        self.assertTrue(scheduled)
        await asyncio.wait_for(socket.delivered.wait(), timeout=1)
        self.assertEqual(1, hub.stats()["scheduled"])
        self.assertEqual(4, json.loads(socket.sent[0])["data"]["task_id"])

    async def test_unbound_loop_failure_is_explicit_and_counted(self):
        hub = Hub()
        with self.assertLogs("sjzq.realtime_ws", level="ERROR"):
            self.assertFalse(hub.schedule(RealtimeChannel(1, 2, 3), "task_log", {}))
        self.assertEqual(1, hub.stats()["schedule_failures"])


class HandshakeTests(unittest.IsolatedAsyncioTestCase):
    async def test_valid_first_frame_connects_and_returns_ready(self):
        socket = _Socket(inbound=[json.dumps({"type": "auth", "token": "token", "device_id": 33})])
        channel = RealtimeChannel(11, 22, 33)
        with patch.object(ws_hub, "authorize_realtime", return_value=channel):
            await ws_hub.realtime(socket)
        self.assertTrue(socket.accepted)
        self.assertEqual("ready", json.loads(socket.sent[0])["event"])
        self.assertNotIn(channel, ws_hub.hub.clients)

    async def test_missing_or_invalid_credentials_close_with_policy_violation(self):
        cases = {
            "missing_token": {"type": "auth", "device_id": 33},
            "missing_device": {"type": "auth", "token": "token"},
            "boolean_device": {"type": "auth", "token": "token", "device_id": True},
            "wrong_frame": {"type": "ping"},
        }
        for case, payload in cases.items():
            with self.subTest(case=case):
                socket = _Socket(inbound=[json.dumps(payload)])
                with self.assertLogs("sjzq.realtime_ws", level="WARNING"):
                    await ws_hub.realtime(socket)
                self.assertEqual(1008, socket.closed[0])

    async def test_permission_tenant_revocation_and_resource_failures_are_indistinguishable(self):
        for case in (
            "insufficient_permission",
            "cross_tenant",
            "revoked_device",
            "workspace_membership",
            "resource_mismatch",
        ):
            with self.subTest(case=case):
                socket = _Socket(inbound=[json.dumps({"type": "auth", "token": "token", "device_id": 33})])
                with patch.object(ws_hub, "authorize_realtime", side_effect=RealtimeAuthError), \
                        self.assertLogs("sjzq.realtime_ws", level="WARNING"):
                    await ws_hub.realtime(socket)
                self.assertEqual((1008, "authorization failed"), socket.closed)


if __name__ == "__main__":
    unittest.main()
