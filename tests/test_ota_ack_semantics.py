"""OTA acknowledgement is delivery-only; heartbeat version confirms installation."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from server.cast_state import CastState
from server.routers import devices, ota
from server.schemas import DeviceHeartbeatIn


class _Cursor:
    rowcount = 1

    def execute(self, *_args, **_kwargs):
        return None


class _Conn:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return _Cursor()


class OtaAckSemanticsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.state = CastState()
        self.scope = (301, 401)
        self.device = {
            "device_id": 71,
            "device_key": "device-ota-semantics",
            "enterprise_id": self.scope[0],
            "workspace_id": self.scope[1],
            "current_task_id": None,
        }
        self.state.push_apk_update(
            {"version_name": "1.0.82", "version_code": 82, "size": 12345},
            [self.device["device_key"]],
            scope=self.scope,
        )

    def test_ack_endpoint_does_not_confirm_install_and_matching_heartbeat_does(self) -> None:
        # A start/download acknowledgement must leave the command pending: Android's
        # system installer still requires an out-of-process user confirmation.
        with patch.object(ota, "get_conn", return_value=_Conn()), \
             patch.object(ota, "get_device_by_key", return_value=self.device), \
             patch.object(ota, "cast_state", self.state):
            response = ota.ack_update(ota.OtaAckIn(
                device_key=self.device["device_key"], version_name="1.0.82",
            ))
        self.assertTrue(response.ok)
        self.assertEqual(1, self.state.get_pending_apk(self.scope)["pending_devices"])

        # Only a heartbeat emitted by the newly installed BuildConfig version may
        # consume the OTA command.
        request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
        with patch.object(devices, "get_conn", return_value=_Conn()), \
             patch.object(devices, "get_device_by_key", side_effect=[self.device, self.device]), \
             patch.object(devices, "enrich_device", return_value={"device_id": 71}), \
             patch.object(devices, "latest_payload", return_value={"has_apk": False}), \
             patch.object(devices, "cast_state", self.state):
            response = devices.heartbeat(DeviceHeartbeatIn(
                device_key=self.device["device_key"], app_version="1.0.82", ota_generation=1,
            ), request)
        self.assertIsNone(response.data["commands"]["update_apk"])
        self.assertIsNone(self.state.get_pending_apk(self.scope))

    def test_stale_generation_cannot_consume_replacement_push(self) -> None:
        self.state.push_apk_update({"version_name": "1.0.83"}, [self.device["device_key"]], self.scope)
        self.assertFalse(self.state.confirm_apk_install(self.device["device_key"], "1.0.82", 1, self.scope))
        self.assertEqual(2, self.state.get_pending_apk(self.scope)["generation"])
        self.assertFalse(self.state.confirm_apk_install(self.device["device_key"], "1.0.83", 1, self.scope))
        self.assertTrue(self.state.confirm_apk_install(self.device["device_key"], "1.0.83", 2, self.scope))


if __name__ == "__main__":
    unittest.main()
