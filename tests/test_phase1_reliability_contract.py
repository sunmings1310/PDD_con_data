from __future__ import annotations

import json
import asyncio
import hashlib
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from server.routers import products, tasks
from server.product_observation import QuarantineResult
from server.schemas import ProductUploadIn, TaskFinishIn


DEVICE = {"device_id": 7, "device_key": "device-key"}


class SequenceCursor:
    def __init__(self, rows):
        self.rows = list(rows)
        self.sql = []

    def execute(self, sql, params=None):
        self.sql.append((" ".join(sql.split()), params or {}))

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None


class Connection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


def conn_factory(conn):
    @contextmanager
    def factory():
        yield conn

    return factory


class FakeUpload:
    def __init__(self, filename: str, raw: bytes, content_type: str = "image/jpeg"):
        self.filename = filename
        self.raw = raw
        self.content_type = content_type

    async def read(self):
        return self.raw


def valid_product(**overrides):
    values = dict(
        device_key="device-key",
        task_id=22,
        idempotency_key="product-22-a",
        platform_code="pinduoduo",
        item_id="123456789",
        sell_name="测试商品",
        item_url="https://mobile.yangkeduo.com/goods.html?goods_id=123456789",
        price=12.3,
        page_status="product",
        parse_status="success",
        quality_status="passed",
        field_sources={"item_id": "detail", "price": "detail"},
        parser_version="pdd-android-1",
        quality_rules_version="phase1-1",
    )
    values.update(overrides)
    return ProductUploadIn(**values)


class Phase1ReliabilityContractTest(unittest.TestCase):
    def test_abnormal_page_is_quarantined_before_normal_product_write(self):
        body = valid_product(page_status="login_required")
        cursor = SequenceCursor([None])
        with patch.object(products, "get_conn", conn_factory(Connection(cursor))), \
             patch.object(products, "get_device_by_key", return_value=DEVICE), \
             patch.object(products, "lock_device"), \
             patch.object(products, "require_running_task", return_value={}), \
             patch.object(products, "persist_quarantine", return_value=QuarantineResult(91, 92, 93)) as persisted:
            response = products.upload_product(body)
        self.assertFalse(response.ok)
        self.assertEqual("QUALITY_REJECTED", response.data["error_code"])
        self.assertEqual(91, response.data["quarantine_id"])
        persisted.assert_called_once()
        self.assertFalse(any("INSERT INTO SJZQ_PRODUCT" in sql for sql, _ in cursor.sql))

    def test_receipt_replay_precedes_newer_quality_rule_rejection(self):
        body = valid_product(page_status="login_required")
        digest = products._product_payload_hash(body)
        result = {"product_id": 101, "acknowledged": True, "persisted": True}
        cursor = SequenceCursor([(digest, 101, "acked", json.dumps(result), 7)])
        with patch.object(products, "get_conn", conn_factory(Connection(cursor))), patch.object(
            products, "get_device_by_key", return_value=DEVICE
        ):
            response = products.upload_product(body)
        self.assertTrue(response.ok)
        self.assertTrue(response.data["idempotent"])
        self.assertTrue(response.data["acknowledged"])
        self.assertFalse(any("INSERT INTO SJZQ_PRODUCT" in sql for sql, _ in cursor.sql))

    def test_product_receipt_replay_returns_same_persisted_product_without_insert(self):
        body = valid_product()
        digest = products._product_payload_hash(body)
        result = {"product_id": 101, "acknowledged": True, "persisted": True}
        cursor = SequenceCursor([(digest, 101, "acked", json.dumps(result), 7)])
        with patch.object(products, "get_conn", conn_factory(Connection(cursor))), patch.object(
            products, "get_device_by_key", return_value=DEVICE
        ):
            response = products.upload_product(body)
        self.assertTrue(response.ok)
        self.assertEqual(101, response.data["product_id"])
        self.assertTrue(response.data["idempotent"])
        self.assertTrue(response.data["persisted"])
        self.assertFalse(any("INSERT INTO SJZQ_PRODUCT" in sql for sql, _ in cursor.sql))

    def test_same_product_key_with_changed_payload_is_conflict(self):
        body = valid_product(price=13.0)
        cursor = SequenceCursor([("different-sha", 101, "acked", "{}", 7)])
        with patch.object(products, "get_conn", conn_factory(Connection(cursor))), patch.object(
            products, "get_device_by_key", return_value=DEVICE
        ):
            response = products.upload_product(body)
        self.assertFalse(response.ok)
        self.assertEqual("IDEMPOTENCY_CONFLICT", response.data["error_code"])

    def test_finish_manifest_mismatch_cannot_complete_task(self):
        cursor = SequenceCursor([None, (0, 0)])
        body = TaskFinishIn(
            device_key="device-key",
            task_id=22,
            status="complete",
            finish_id="finish-22-1",
            expected_product_count=1,
            expected_image_count=0,
        )
        with patch.object(tasks, "get_conn", conn_factory(Connection(cursor))), patch.object(
            tasks, "get_device_by_key", return_value=DEVICE
        ), patch.object(tasks, "lock_device"), patch.object(tasks, "require_running_task", return_value={}):
            response = tasks.task_finish(body)
        self.assertFalse(response.ok)
        self.assertEqual("FINISH_INCOMPLETE", response.data["error_code"])
        self.assertFalse(any("UPDATE SJZQ_TASK SET STATUS" in sql for sql, _ in cursor.sql))

    def test_finish_receipt_replay_does_not_repeat_transition(self):
        body = TaskFinishIn(
            device_key="device-key",
            task_id=22,
            status="complete",
            finish_id="finish-22-1",
            expected_product_count=1,
            expected_image_count=0,
        )
        finish_payload = {
            "task_id": 22,
            "status": "complete",
            "error_msg": None,
            "expected_product_count": 1,
            "expected_image_count": 0,
        }
        import hashlib

        digest = hashlib.sha256(
            json.dumps(finish_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        cursor = SequenceCursor([(digest, "acked", json.dumps({"status": "succeeded"}), 7)])
        with patch.object(tasks, "get_conn", conn_factory(Connection(cursor))), patch.object(
            tasks, "get_device_by_key", return_value=DEVICE
        ), patch.object(tasks, "transition_task", side_effect=AssertionError("must not transition")):
            response = tasks.task_finish(body)
        self.assertTrue(response.ok)
        self.assertTrue(response.data["idempotent"])
        self.assertTrue(response.data["acknowledged"])

    def test_image_receipt_replay_returns_original_ack_without_new_insert(self):
        upload = FakeUpload("a.jpg", b"phase1-image")
        digest = hashlib.sha256()
        digest.update(b"101")
        digest.update(upload.filename.encode())
        digest.update(upload.content_type.encode())
        digest.update(hashlib.sha256(upload.raw).digest())
        result = {"product_id": 101, "images": [{"image_id": 5}], "skipped_license": []}
        cursor = SequenceCursor([(digest.hexdigest(), 101, "acked", json.dumps(result), 7)])
        with patch.object(products, "get_conn", conn_factory(Connection(cursor))), patch.object(
            products, "get_device_by_key", return_value=DEVICE
        ), patch.object(products, "row_as_dict", return_value={"product_id": 101, "platform_code": "pinduoduo"}):
            response = asyncio.run(
                products.upload_images(101, "device-key", "product-101:images", [upload])
            )
        self.assertTrue(response.ok)
        self.assertTrue(response.data["acknowledged"])
        self.assertTrue(response.data["idempotent"])
        self.assertFalse(any("INSERT INTO SJZQ_PRODUCT_IMAGE" in sql for sql, _ in cursor.sql))

    def test_image_key_payload_conflict_is_rejected(self):
        upload = FakeUpload("a.jpg", b"changed")
        cursor = SequenceCursor([("different-sha", 101, "acked", "{}", 7)])
        with patch.object(products, "get_conn", conn_factory(Connection(cursor))), patch.object(
            products, "get_device_by_key", return_value=DEVICE
        ), patch.object(products, "row_as_dict", return_value={"product_id": 101, "platform_code": "pinduoduo"}):
            response = asyncio.run(
                products.upload_images(101, "device-key", "product-101:images", [upload])
            )
        self.assertFalse(response.ok)
        self.assertEqual("IDEMPOTENCY_CONFLICT", response.data["error_code"])


if __name__ == "__main__":
    unittest.main()
