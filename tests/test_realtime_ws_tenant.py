"""Offline contract tests for tenant-scoped realtime WebSocket delivery."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import unittest
from contextlib import contextmanager
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
from server.ws_hub import (  # noqa: E402
    Hub,
    RealtimeAuthError,
    RealtimeChannel,
    RealtimePrincipal,
)


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

    def test_scope_mismatch_does_not_consume_progress_receipt_before_retry(self):
        from server.routers import tasks
        from server.schemas import TaskProgressIn

        receipts: set[str] = set()
        channel = RealtimeChannel(1, 2, 7)

        class Cursor:
            def execute(self, _sql, _binds=None):
                pass

        class Connection:
            def cursor(self):
                return Cursor()

        @contextmanager
        def connection():
            yield Connection()

        def claim(_cur, progress_id, _task_id, _device_id):
            if progress_id in receipts:
                return False
            receipts.add(progress_id)
            return True

        body = TaskProgressIn(
            device_key="device-key",
            task_id=22,
            message="delta",
            success_delta=1,
            progress_id="progress-retry-1",
        )
        common = (
            patch.object(tasks, "get_conn", connection),
            patch.object(tasks, "get_device_by_key", return_value={"device_id": 7}),
            patch.object(tasks, "lock_device", return_value={}),
            patch.object(tasks, "require_running_task", return_value={}),
            patch.object(tasks, "_has_collection_jobs", return_value=False),
            patch.object(tasks, "claim_progress_id", side_effect=claim),
            patch.object(tasks, "append_task_log", return_value=None),
            patch.object(tasks, "notify_sync", return_value=True),
        )
        with common[0], common[1], common[2], common[3], common[4], common[5], common[6], common[7], \
                patch.object(tasks, "resolve_task_event_channel", return_value=None):
            first = tasks.task_progress(body)
        self.assertFalse(first.ok)
        self.assertEqual(set(), receipts)

        common_retry = (
            patch.object(tasks, "get_conn", connection),
            patch.object(tasks, "get_device_by_key", return_value={"device_id": 7}),
            patch.object(tasks, "lock_device", return_value={}),
            patch.object(tasks, "require_running_task", return_value={}),
            patch.object(tasks, "_has_collection_jobs", return_value=False),
            patch.object(tasks, "claim_progress_id", side_effect=claim),
            patch.object(tasks, "append_task_log", return_value=None),
            patch.object(tasks, "notify_sync", return_value=True),
            patch.object(tasks, "resolve_task_event_channel", return_value=channel),
        )
        with common_retry[0], common_retry[1], common_retry[2], common_retry[3], common_retry[4], \
                common_retry[5], common_retry[6], common_retry[7], common_retry[8]:
            retry = tasks.task_progress(body)
        self.assertTrue(retry.ok)
        self.assertEqual({"progress-retry-1"}, receipts)


class HubIsolationTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def principal(channel, user_id=7, expires_at=4102444800):
        return RealtimePrincipal(user_id, expires_at, channel)

    async def test_only_same_tenant_workspace_and_device_receives(self):
        hub = Hub(validator=lambda _principal: True)
        target = RealtimeChannel(1, 2, 3)
        same = _Socket()
        other_tenant = _Socket()
        other_workspace = _Socket()
        other_device = _Socket()
        await hub.connect(same, self.principal(target))
        await hub.connect(other_tenant, self.principal(RealtimeChannel(9, 2, 3)))
        await hub.connect(other_workspace, self.principal(RealtimeChannel(1, 9, 3)))
        await hub.connect(other_device, self.principal(RealtimeChannel(1, 2, 9)))
        await hub.broadcast(target, "task_log", {"task_id": 4})
        self.assertEqual(1, len(same.sent))
        self.assertEqual([], other_tenant.sent)
        self.assertEqual([], other_workspace.sent)
        self.assertEqual([], other_device.sent)

    async def test_delivery_failure_is_counted_and_failed_peer_removed(self):
        hub = Hub(validator=lambda _principal: True)
        channel = RealtimeChannel(1, 2, 3)
        failed = _Socket(fail_send=True)
        await hub.connect(failed, self.principal(channel))
        with self.assertLogs("sjzq.realtime_ws", level="ERROR"):
            await hub.broadcast(channel, "task_log", {})
        self.assertEqual(1, hub.stats()["delivery_failures"])
        self.assertNotIn(channel, hub.clients)

    async def test_worker_thread_schedules_on_bound_app_loop(self):
        hub = Hub(validator=lambda _principal: True)
        channel = RealtimeChannel(1, 2, 3)
        socket = _Socket()
        await hub.connect(socket, self.principal(channel))
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

    async def test_closed_loop_failure_is_explicit_and_counted(self):
        hub = Hub()
        closed_loop = asyncio.new_event_loop()
        closed_loop.close()
        hub.bind_loop(closed_loop)
        with self.assertLogs("sjzq.realtime_ws", level="ERROR"):
            self.assertFalse(hub.schedule(RealtimeChannel(1, 2, 3), "task_log", {}))
        self.assertEqual(1, hub.stats()["schedule_failures"])

    async def test_membership_revoke_after_connect_closes_before_next_delivery(self):
        authorization = {"active": True}
        hub = Hub(validator=lambda _principal: authorization["active"])
        channel = RealtimeChannel(1, 2, 3)
        socket = _Socket()
        await hub.connect(socket, self.principal(channel))
        await hub.broadcast(channel, "task_log", {"sequence": 1})
        self.assertEqual(1, len(socket.sent))

        authorization["active"] = False
        with self.assertLogs("sjzq.realtime_ws", level="WARNING"):
            await hub.broadcast(channel, "task_log", {"sequence": 2})
        self.assertEqual(1, len(socket.sent))
        self.assertEqual((1008, "authorization revoked"), socket.closed)
        self.assertNotIn(channel, hub.clients)

    async def test_expired_token_cannot_be_kept_alive_by_ping(self):
        expired = RealtimePrincipal(7, 1, RealtimeChannel(1, 2, 3))
        self.assertFalse(ws_hub.revalidate_realtime(expired))


class HandshakeTests(unittest.IsolatedAsyncioTestCase):
    async def test_valid_first_frame_connects_and_returns_ready(self):
        socket = _Socket(inbound=[json.dumps({"type": "auth", "token": "token", "device_id": 33})])
        channel = RealtimeChannel(11, 22, 33)
        principal = RealtimePrincipal(7, 4102444800, channel)
        with patch.object(ws_hub, "authorize_realtime", return_value=principal):
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
