"""Phase 5.5 final gates against an isolated real Oracle schema."""

from __future__ import annotations

import asyncio
import os
import threading
import time
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import oracledb
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

for _key, _value in {
    "APP_ENV": "test", "ORACLE_HOST": "127.0.0.1", "ORACLE_PORT": "1521",
    "ORACLE_SERVICE": "TEST", "ORACLE_USER": "TEST", "ORACLE_PASSWORD": "test-password",
    "JWT_SECRET": "Test-only-JWT-secret-32-characters!",
}.items():
    os.environ.setdefault(_key, _value)

from server import management_queries  # noqa: E402
from server.cast_state import cast_state  # noqa: E402
from server.db import close_pool, get_conn, init_pool, next_id  # noqa: E402
from server.device_enrollment import issue  # noqa: E402
from server.auth_util import create_token  # noqa: E402
from server.job_service import create_jobs_for_task  # noqa: E402
from server.main import tenant_media  # noqa: E402
from server.media_access import _signature, signed_media_url  # noqa: E402
from server.ota_meta import apk_dir, save_meta  # noqa: E402
from server.quota import (ACTIVE_TASK, DAILY_SNAPSHOT, STORAGE_BYTES, QuotaExceeded,
                          commit, period_key, release, reserve, reserve_and_commit)  # noqa: E402
from server.routers import cast, dashboard, devices, excel_match, jobs, ota, products, tasks  # noqa: E402
from server.schemas import DeviceHeartbeatIn, DeviceRegisterIn, JobAcquireIn, TaskCreateIn
from server.task_creation_service import create_canonical_task  # noqa: E402
from server.tenant import TenantContext  # noqa: E402

ENABLED = os.getenv("PHASE55_ORACLE_TEST_ENABLED") == "1"


class _Socket:
    def __init__(self):
        self.messages: list[str] = []
        self.closed = False

    async def send_text(self, value: str):
        self.messages.append(value)

    async def close(self, code: int = 1000):
        self.closed = True


@unittest.skipUnless(ENABLED, "Phase 5.5 Oracle sandbox test not enabled")
class Phase55OracleFinalGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_pool()

    @classmethod
    def tearDownClass(cls):
        close_pool()

    def _seq(self, cur, name: str) -> int:
        return next_id(cur, name)

    def _tenant(self, cur, *, active=10, daily=10, storage=10000):
        enterprise_id = self._seq(cur, "SJZQ_SEQ_ENTERPRISE")
        workspace_id = self._seq(cur, "SJZQ_SEQ_WORKSPACE")
        tag = uuid.uuid4().hex[:12]
        cur.execute("""INSERT INTO SJZQ_ENTERPRISE
            (ENTERPRISE_ID,ENTERPRISE_CODE,ENTERPRISE_NAME) VALUES (:id,:code,:name)""",
                    {"id": enterprise_id, "code": "p55-" + tag, "name": "P55 " + tag})
        cur.execute("""INSERT INTO SJZQ_WORKSPACE
            (WORKSPACE_ID,ENTERPRISE_ID,WORKSPACE_CODE,WORKSPACE_NAME)
            VALUES (:workspace_id,:enterprise_id,'main','Main')""",
                    {"workspace_id": workspace_id, "enterprise_id": enterprise_id})
        cur.execute("""INSERT INTO SJZQ_ENTERPRISE_QUOTA
            (ENTERPRISE_ID,MAX_ACTIVE_TASKS,MAX_DAILY_SNAPSHOTS,STORAGE_BYTES)
            VALUES (:enterprise_id,:active,:daily,:storage)""",
                    {"enterprise_id": enterprise_id, "active": active,
                     "daily": daily, "storage": storage})
        return enterprise_id, workspace_id

    def _ctx(self, enterprise_id: int, workspace_id: int) -> TenantContext:
        return TenantContext(enterprise_id, workspace_id, 1, 1, "super_admin",
                             frozenset({"task:view", "data:view", "device:manage", "device:cast"}))

    def _cleanup_task_import_fixture(self, cur, enterprise_id: int, workspace_id: int):
        """Remove every durable row created by the canonical-import fixtures."""
        task_scope = "SELECT TASK_ID FROM SJZQ_TASK WHERE ENTERPRISE_ID=:e AND WORKSPACE_ID=:w"
        job_scope = f"SELECT JOB_ID FROM SJZQ_COLLECTION_JOB WHERE TASK_ID IN ({task_scope})"
        scoped_binds = {"e": enterprise_id, "w": workspace_id}
        enterprise_binds = {"e": enterprise_id}
        for sql, binds in (
            (f"DELETE FROM SJZQ_COLLECTION_LEASE WHERE JOB_ID IN ({job_scope})", scoped_binds),
            (f"DELETE FROM SJZQ_COLLECTION_CHECKPOINT WHERE JOB_ID IN ({job_scope})", scoped_binds),
            (f"DELETE FROM SJZQ_COLLECTION_ATTEMPT WHERE JOB_ID IN ({job_scope})", scoped_binds),
            (f"DELETE FROM SJZQ_COLLECTION_OUTBOX WHERE TASK_ID IN ({task_scope})", scoped_binds),
            (f"DELETE FROM SJZQ_JOB_EVENT WHERE TASK_ID IN ({task_scope})", scoped_binds),
            (f"DELETE FROM SJZQ_COLLECTION_JOB WHERE TASK_ID IN ({task_scope})", scoped_binds),
            (f"DELETE FROM SJZQ_TASK_ITEM WHERE TASK_ID IN ({task_scope})", scoped_binds),
            (f"DELETE FROM SJZQ_TASK_LOG WHERE TASK_ID IN ({task_scope})", scoped_binds),
            ("DELETE FROM SJZQ_TASK WHERE ENTERPRISE_ID=:e AND WORKSPACE_ID=:w", scoped_binds),
            ("DELETE FROM SJZQ_QUOTA_LEDGER WHERE ENTERPRISE_ID=:e", enterprise_binds),
            ("DELETE FROM SJZQ_QUOTA_RESERVATION WHERE ENTERPRISE_ID=:e", enterprise_binds),
            ("DELETE FROM SJZQ_QUOTA_USAGE WHERE ENTERPRISE_ID=:e", enterprise_binds),
            ("DELETE FROM SJZQ_WORKSPACE_MEMBERSHIP WHERE ENTERPRISE_ID=:e AND WORKSPACE_ID=:w", scoped_binds),
            ("DELETE FROM SJZQ_ENTERPRISE_MEMBERSHIP WHERE ENTERPRISE_ID=:e", enterprise_binds),
            ("DELETE FROM SJZQ_WORKSPACE WHERE WORKSPACE_ID=:w AND ENTERPRISE_ID=:e", scoped_binds),
            ("DELETE FROM SJZQ_ENTERPRISE_QUOTA WHERE ENTERPRISE_ID=:e", enterprise_binds),
            ("DELETE FROM SJZQ_ENTERPRISE WHERE ENTERPRISE_ID=:e", enterprise_binds),
        ):
            cur.execute(sql, binds)
        for table, predicate, binds in (
            ("SJZQ_TASK", "ENTERPRISE_ID=:e AND WORKSPACE_ID=:w", scoped_binds),
            ("SJZQ_TASK_ITEM", "TASK_ID IN (SELECT TASK_ID FROM SJZQ_TASK WHERE ENTERPRISE_ID=:e AND WORKSPACE_ID=:w)", scoped_binds),
            ("SJZQ_COLLECTION_JOB", "TASK_ID IN (SELECT TASK_ID FROM SJZQ_TASK WHERE ENTERPRISE_ID=:e AND WORKSPACE_ID=:w)", scoped_binds),
            ("SJZQ_QUOTA_USAGE", "ENTERPRISE_ID=:e", enterprise_binds),
            ("SJZQ_ENTERPRISE", "ENTERPRISE_ID=:e", enterprise_binds),
        ):
            cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {predicate}", binds)
            self.assertEqual(0, int(cur.fetchone()[0] or 0), table)

    def test_01_migration_first_run_and_rerun_are_applied(self):
        from server.migrate import ensure_schema_patches

        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""SELECT STATUS,CHECKSUM,APPLIED_AT FROM SJZQ_SCHEMA_MIGRATION
                             WHERE VERSION_ID='P5_5_001_ENTERPRISE_HARDENING'""")
            first = cur.fetchone()
            self.assertEqual("applied", str(first[0]).lower())
            self.assertEqual(64, len(str(first[1])))
            cur.execute("""SELECT COUNT(*) FROM USER_TABLES WHERE TABLE_NAME IN
                ('SJZQ_DEVICE_ENROLL_TOKEN','SJZQ_QUOTA_USAGE','SJZQ_QUOTA_RESERVATION','SJZQ_QUOTA_LEDGER')""")
            self.assertEqual(4, int(cur.fetchone()[0]))
        ensure_schema_patches()
        ensure_schema_patches()
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""SELECT STATUS,CHECKSUM,APPLIED_AT FROM SJZQ_SCHEMA_MIGRATION
                             WHERE VERSION_ID='P5_5_001_ENTERPRISE_HARDENING'""")
            rerun = cur.fetchone()
            self.assertEqual(first, rerun)

    def test_02_two_enterprises_are_isolated_on_all_read_surfaces(self):
        marker = "isolation-" + uuid.uuid4().hex[:12]
        with get_conn() as conn:
            cur = conn.cursor()
            ea, wa = self._tenant(cur)
            eb, wb = self._tenant(cur)
            ta, tb = self._seq(cur, "SJZQ_SEQ_TASK"), self._seq(cur, "SJZQ_SEQ_TASK")
            for task_id, enterprise_id, workspace_id, suffix in ((ta, ea, wa, "A"), (tb, eb, wb, "B")):
                cur.execute("""INSERT INTO SJZQ_TASK
                    (TASK_ID,TASK_NAME,TASK_TYPE,PLATFORM_CODE,STATUS,PRIORITY,TARGET_COUNT,
                     REVIEW_STATUS,ENTERPRISE_ID,WORKSPACE_ID)
                    VALUES (:id,:name,'collect','pinduoduo','pending',5,0,'approved',:e,:w)""",
                            {"id": task_id, "name": marker + suffix, "e": enterprise_id, "w": workspace_id})
            pa, pb = self._seq(cur, "SJZQ_SEQ_PRODUCT"), self._seq(cur, "SJZQ_SEQ_PRODUCT")
            for product_id, task_id, enterprise_id, workspace_id, suffix in (
                    (pa, ta, ea, wa, "A"), (pb, tb, eb, wb, "B")):
                cur.execute("""INSERT INTO SJZQ_PRODUCT
                    (PRODUCT_ID,TASK_ID,PLATFORM_CODE,KEYWORD,ITEM_ID,PRODUCT_NAME,PRICE,
                     LIBRARY_STATUS,ENTERPRISE_ID,WORKSPACE_ID)
                    VALUES (:id,:task,'pinduoduo',:keyword,:item,:name,1,:library_status,:e,:w)""",
                            {"id": product_id, "task": task_id, "keyword": marker,
                             "item": marker + suffix, "name": marker + suffix,
                             "library_status": "saved",
                             "e": enterprise_id, "w": workspace_id})

            resources = []
            for enterprise_id, workspace_id, task_id, product_id, suffix in (
                    (ea, wa, ta, pa, "A"), (eb, wb, tb, pb, "B")):
                master = self._seq(cur, "SJZQ_SEQ_PRODUCT_MASTER")
                enterprise_product = self._seq(cur, "SJZQ_SEQ_ENTERPRISE_PRODUCT")
                raw = self._seq(cur, "SJZQ_SEQ_RAW_COLLECTION")
                snapshot = self._seq(cur, "SJZQ_SEQ_PRODUCT_SNAPSHOT")
                snapshot_quality = self._seq(cur, "SJZQ_SEQ_QUALITY_RESULT")
                qraw = self._seq(cur, "SJZQ_SEQ_RAW_COLLECTION")
                quality = self._seq(cur, "SJZQ_SEQ_QUALITY_RESULT")
                quarantine = self._seq(cur, "SJZQ_SEQ_DATA_QUARANTINE")
                cur.execute("""INSERT INTO SJZQ_PRODUCT_MASTER
                    (MASTER_PRODUCT_ID,PLATFORM_CODE,PLATFORM_PRODUCT_ID)
                    VALUES (:id,'pinduoduo',:item)""", {"id": master, "item": marker + suffix})
                cur.execute("""INSERT INTO SJZQ_ENTERPRISE_PRODUCT
                    (ENTERPRISE_PRODUCT_ID,ENTERPRISE_ID,IDENTITY_ID)
                    VALUES (:id,:e,:master)""", {"id": enterprise_product, "e": enterprise_id, "master": master})
                cur.execute("""INSERT INTO SJZQ_RAW_COLLECTION
                    (RAW_ID,REQUEST_KEY,TASK_ID,SOURCE_TYPE,PAYLOAD_SHA256,RAW_JSON,COLLECTED_AT,ENTERPRISE_ID,WORKSPACE_ID)
                    VALUES (:id,:request_key,:task_id,'product',RPAD('a',64,'a'),'{}',SYSTIMESTAMP,:e,:w)""",
                            {"id": raw, "request_key": marker + "-snap-" + suffix,
                             "task_id": task_id,
                             "e": enterprise_id, "w": workspace_id})
                cur.execute("""INSERT INTO SJZQ_PRODUCT_SNAPSHOT
                    (SNAPSHOT_ID,MASTER_PRODUCT_ID,RAW_ID,LEGACY_PRODUCT_ID,TASK_ID,REQUEST_KEY,COLLECTED_AT,CONTENT_SHA256,
                     NORMALIZED_JSON,TITLE,ENTERPRISE_ID,WORKSPACE_ID,ENTERPRISE_PRODUCT_ID)
                    VALUES (:id,:master,:raw_id,:product_id,:task_id,:request_key,SYSTIMESTAMP,RPAD('b',64,'b'),'{}',:title,:e,:w,:ep)""",
                            {"id": snapshot, "master": master, "raw_id": raw, "product_id": product_id,
                             "task_id": task_id,
                             "request_key": marker + "-snapshot-" + suffix, "title": marker + suffix,
                             "e": enterprise_id, "w": workspace_id, "ep": enterprise_product})
                cur.execute("""INSERT INTO SJZQ_QUALITY_RESULT
                    (QUALITY_RESULT_ID,RAW_ID,SNAPSHOT_ID,ACCEPTED,STATUS,PAGE_STATUS,PARSE_STATUS,QUALITY_STATUS,
                     PARSER_VERSION,QUALITY_RULES_VERSION,ENTERPRISE_ID,WORKSPACE_ID)
                    VALUES (:id,:raw_id,:snapshot_id,1,'accepted','product','success','passed','p55','p55',:e,:w)""",
                            {"id": snapshot_quality, "raw_id": raw, "snapshot_id": snapshot,
                             "e": enterprise_id, "w": workspace_id})
                cur.execute("""UPDATE SJZQ_PRODUCT
                                  SET MASTER_PRODUCT_ID=:master,SNAPSHOT_ID=:snapshot,
                                      ENTERPRISE_PRODUCT_ID=:enterprise_product
                                WHERE PRODUCT_ID=:product_id""",
                            {"master": master, "snapshot": snapshot,
                             "enterprise_product": enterprise_product, "product_id": product_id})
                cur.execute("""INSERT INTO SJZQ_RAW_COLLECTION
                    (RAW_ID,REQUEST_KEY,TASK_ID,SOURCE_TYPE,PAYLOAD_SHA256,RAW_JSON,COLLECTED_AT,ENTERPRISE_ID,WORKSPACE_ID)
                    VALUES (:id,:request_key,:task_id,'product',RPAD('c',64,'c'),'{}',SYSTIMESTAMP,:e,:w)""",
                            {"id": qraw, "request_key": marker + "-raw-" + suffix,
                             "task_id": task_id,
                             "e": enterprise_id, "w": workspace_id})
                cur.execute("""INSERT INTO SJZQ_QUALITY_RESULT
                    (QUALITY_RESULT_ID,RAW_ID,ACCEPTED,STATUS,PAGE_STATUS,PARSE_STATUS,QUALITY_STATUS,
                     PARSER_VERSION,QUALITY_RULES_VERSION,ENTERPRISE_ID,WORKSPACE_ID)
                    VALUES (:id,:raw_id,0,'rejected','normal','success','rejected','p55','p55',:e,:w)""",
                            {"id": quality, "raw_id": qraw, "e": enterprise_id, "w": workspace_id})
                cur.execute("""INSERT INTO SJZQ_DATA_QUARANTINE
                    (QUARANTINE_ID,RAW_ID,QUALITY_RESULT_ID,MASTER_PRODUCT_ID,TASK_ID,REQUEST_KEY,
                     STATUS,FAILURE_REASON,COLLECTED_AT,ENTERPRISE_ID,WORKSPACE_ID,ENTERPRISE_PRODUCT_ID)
                    VALUES (:id,:raw_id,:quality,:master,:task,:request_key,'open',:reason,SYSTIMESTAMP,:e,:w,:ep)""",
                            {"id": quarantine, "raw_id": qraw, "quality": quality, "master": master,
                             "task": task_id, "request_key": marker + "-quarantine-" + suffix,
                             "reason": marker + suffix, "e": enterprise_id, "w": workspace_id,
                             "ep": enterprise_product})
                resources.append((enterprise_product, snapshot, quarantine, raw, snapshot_quality,
                                  qraw, quality, product_id, master))

        ctx_a, ctx_b = self._ctx(ea, wa), self._ctx(eb, wb)
        user = {"user_id": 1}
        page_a = tasks.list_tasks(page=1, limit=1, user=user, tenant=ctx_a).data
        self.assertEqual((1, [ta]), (page_a["total"], [int(x["task_id"]) for x in page_a["items"]]))
        self.assertFalse(tasks.get_task(tb, user=user, tenant=ctx_a).ok)
        search_a = products.list_products(keyword=marker, page=1, limit=10, tenant=ctx_a).data
        self.assertEqual([pa], [int(x["product_id"]) for x in search_a["items"]])
        self.assertEqual(1, dashboard.summary(tenant=ctx_a).data["pending_tasks"])
        with get_conn() as conn:
            cur = conn.cursor()
            job_id = create_jobs_for_task(cur, task_id=ta)[0]
            attempt_id = self._seq(cur, "SJZQ_SEQ_COLLECTION_ATTEMPT")
            lease_hash = uuid.uuid4().hex + uuid.uuid4().hex
            cur.execute("""INSERT INTO SJZQ_COLLECTION_ATTEMPT
                (ATTEMPT_ID,JOB_ID,ATTEMPT_NO,LEASE_TOKEN_HASH,TRACE_ID,STATUS,
                 LEASE_EXPIRES_AT,FINISHED_AT,FINAL_CHECKPOINT_VERSION,ENTERPRISE_ID,WORKSPACE_ID)
                VALUES (:attempt_id,:job_id,1,:lease_hash,:trace_id,'success',
                        SYSTIMESTAMP,SYSTIMESTAMP,0,:enterprise_id,:workspace_id)""",
                        {"attempt_id": attempt_id, "job_id": job_id, "lease_hash": lease_hash,
                         "trace_id": marker + "-trace", "enterprise_id": ea, "workspace_id": wa})
            cur.execute("""UPDATE SJZQ_RAW_COLLECTION
                              SET JOB_ID=:job_id,ATTEMPT_ID=:attempt_id
                            WHERE RAW_ID=:raw_id""",
                        {"job_id": job_id, "attempt_id": attempt_id, "raw_id": resources[0][3]})
            cur.execute("""UPDATE SJZQ_PRODUCT_SNAPSHOT
                              SET JOB_ID=:job_id,ATTEMPT_ID=:attempt_id
                            WHERE SNAPSHOT_ID=:snapshot_id""",
                        {"job_id": job_id, "attempt_id": attempt_id, "snapshot_id": resources[0][1]})
            cur.execute("""UPDATE SJZQ_COLLECTION_JOB
                              SET STATUS='retry_wait',ATTEMPT_COUNT=1,NEXT_RUN_AT=SYSTIMESTAMP
                            WHERE JOB_ID=:job_id""",
                        {"job_id": job_id})
            self.assertIsNotNone(management_queries.task_trace(cur, ta, tenant=ctx_a))
            self.assertIsNone(management_queries.task_trace(cur, tb, tenant=ctx_a))
            own_snapshots = management_queries.list_snapshots(cur, resources[0][0], page=1, limit=10, tenant=ctx_a)
            cross_snapshots = management_queries.list_snapshots(cur, resources[1][0], page=1, limit=10, tenant=ctx_a)
            self.assertEqual((1, 0), (own_snapshots["total"], cross_snapshots["total"]))
            cur.execute("UPDATE SJZQ_PRODUCT SET LIBRARY_STATUS='draft' WHERE PRODUCT_ID=:product_id",
                        {"product_id": resources[0][7]})
            task_result_page = management_queries.task_results(cur, ta, page=1, limit=10, tenant=ctx_a)
            cross_task_result_page = management_queries.task_results(cur, tb, page=1, limit=10, tenant=ctx_a)
            self.assertEqual((2, 0), (task_result_page["total"], cross_task_result_page["total"]))
            result_by_kind = {item["result_kind"]: item for item in task_result_page["items"]}
            accepted_result = result_by_kind["snapshot"]
            quarantined_result = result_by_kind["quarantine"]
            self.assertEqual(
                (resources[0][1], resources[0][3], resources[0][4], resources[0][7], "draft", True),
                (int(accepted_result["snapshot_id"]), int(accepted_result["raw_id"]),
                 int(accepted_result["quality_result_id"]), int(accepted_result["product_id"]),
                 accepted_result["library"]["status"], accepted_result["library"]["can_save"]),
            )
            self.assertEqual(
                (resources[0][2], resources[0][5], resources[0][6], "unavailable"),
                (int(quarantined_result["quarantine_id"]), int(quarantined_result["raw_id"]),
                 int(quarantined_result["quality_result_id"]), quarantined_result["library"]["status"]),
            )
            snapshot_resource = management_queries.task_result_resource(
                cur, ta, "snapshot", resources[0][1], tenant=ctx_a)
            raw_resource = management_queries.task_result_resource(
                cur, ta, "raw", resources[0][3], tenant=ctx_a)
            quality_resource = management_queries.task_result_resource(
                cur, ta, "quality", resources[0][4], tenant=ctx_a)
            quarantine_resource = management_queries.task_result_resource(
                cur, ta, "quarantine", resources[0][2], tenant=ctx_a)
            cross_resource = management_queries.task_result_resource(
                cur, ta, "snapshot", resources[1][1], tenant=ctx_a)
            self.assertEqual(
                (resources[0][1], resources[0][3], resources[0][4], resources[0][2], None),
                (snapshot_resource["resource_id"], raw_resource["resource_id"],
                 quality_resource["resource_id"], quarantine_resource["resource_id"], cross_resource),
            )
            task_job_page = management_queries.task_jobs(cur, ta, 1, 10, tenant=ctx_a)
            attempt_page = management_queries.job_attempts(cur, job_id, 1, 10, tenant=ctx_a)
            self.assertEqual(resources[0][1], int(task_job_page["items"][0]["business_results"][0]["snapshot_id"]))
            self.assertEqual(resources[0][3], int(attempt_page["items"][0]["business_results"][0]["raw_id"]))
            own_quarantine = management_queries.list_quarantines(cur, page=1, limit=10,
                                                                  filters={"failure_reason": marker}, tenant=ctx_a)
            other_quarantine = management_queries.list_quarantines(cur, page=1, limit=10,
                                                                    filters={"failure_reason": marker}, tenant=ctx_b)
            self.assertEqual(([resources[0][2]], [resources[1][2]]),
                             ([int(x["quarantine_id"]) for x in own_quarantine["items"]],
                              [int(x["quarantine_id"]) for x in other_quarantine["items"]]))

    def test_03_enrollment_rotation_revoke_and_media_fences(self):
        request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
        with get_conn() as conn:
            cur = conn.cursor()
            enterprise_id, workspace_id = self._tenant(cur)
            other_enterprise, other_workspace = self._tenant(cur)
            _, bearer = issue(cur, enterprise_id=enterprise_id, workspace_id=workspace_id, issued_by=1)
        original_key = "p55-device-" + uuid.uuid4().hex[:12]
        created = devices.register_device(DeviceRegisterIn(device_key=original_key,
                                                            enrollment_token=bearer), request)
        self.assertTrue(created.ok)
        device_id = int(created.data["device_id"])
        replay = devices.register_device(DeviceRegisterIn(device_key=original_key + "-replay",
                                                           enrollment_token=bearer), request)
        self.assertFalse(replay.ok)
        rotated = asyncio.run(devices.rotate_device_key(device_id, tenant=self._ctx(enterprise_id, workspace_id)))
        self.assertTrue(rotated.ok)
        device_key = str(rotated.data["device_key"])
        self.assertFalse(devices.heartbeat(DeviceHeartbeatIn(device_key=original_key), request).ok)
        self.assertTrue(devices.heartbeat(DeviceHeartbeatIn(device_key=device_key), request).ok)

        with get_conn() as conn:
            cur = conn.cursor()
            task_id = self._seq(cur, "SJZQ_SEQ_TASK")
            item_id = self._seq(cur, "SJZQ_SEQ_TASK_ITEM")
            cur.execute("""INSERT INTO SJZQ_TASK
                (TASK_ID,TASK_NAME,TASK_TYPE,PLATFORM_CODE,STATUS,PRIORITY,TARGET_COUNT,
                 REVIEW_STATUS,ENTERPRISE_ID,WORKSPACE_ID)
                VALUES (:id,:name,'collect','pinduoduo','pending',1,1,'approved',:e,:w)""",
                        {"id": task_id, "name": "p55-device-task", "e": enterprise_id, "w": workspace_id})
            cur.execute("""INSERT INTO SJZQ_TASK_ITEM
                (ITEM_ID,TASK_ID,ROW_INDEX,KEYWORD,STATUS,ENTERPRISE_ID,WORKSPACE_ID)
                VALUES (:id,:task,1,'p55','pending',:e,:w)""",
                        {"id": item_id, "task": task_id, "e": enterprise_id, "w": workspace_id})
            create_jobs_for_task(cur, task_id=task_id)
        acquired = jobs.acquire_job(JobAcquireIn(device_key=device_key, worker_id="p55-worker"))
        self.assertTrue(acquired.ok)
        self.assertIsNotNone(acquired.data)

        scope = (enterprise_id, workspace_id)
        apk = apk_dir(scope) / "latest.apk"
        apk.write_bytes(b"phase55-test-apk")
        save_meta("5.5.0", 55, apk.stat().st_size, scope)
        latest = ota.ota_latest(device_key)
        self.assertTrue(latest.ok)
        signed = latest.data["apk_url"]
        parsed, query = urlparse(signed), parse_qs(urlparse(signed).query)
        media_path = parsed.path.removeprefix("/media/")
        args = {key: int(query[key][0]) for key in ("enterprise_id", "workspace_id", "expires", "device_id")}
        signature = query["signature"][0]
        self.assertEqual(device_id, args["device_id"])
        self.assertEqual(200, tenant_media(media_path, signature=signature, **args).status_code)
        with self.assertRaises(HTTPException) as cross:
            tenant_media(media_path, other_enterprise, other_workspace, args["expires"], signature,
                         device_id=device_id)
        self.assertEqual(403, cross.exception.status_code)
        forged_expiry = int(time.time()) + 300
        forged_signature = _signature("../outside.txt", enterprise_id, workspace_id,
                                      forged_expiry, device_id)
        with self.assertRaises(HTTPException) as forged:
            tenant_media("../outside.txt", enterprise_id, workspace_id, forged_expiry,
                         forged_signature, device_id=device_id)
        self.assertEqual(404, forged.exception.status_code)
        expired = int(time.time()) - 1
        expired_signature = _signature(media_path, enterprise_id, workspace_id, expired, device_id)
        with self.assertRaises(HTTPException) as old:
            tenant_media(media_path, enterprise_id, workspace_id, expired, expired_signature,
                         device_id=device_id)
        self.assertEqual(403, old.exception.status_code)

        publisher, viewer = _Socket(), _Socket()
        room = cast_state.ensure_room(device_id, device_key)
        room.publisher = publisher
        room.viewers.add(viewer)
        room.requested = True
        revoked = asyncio.run(devices.revoke_device(device_id, tenant=self._ctx(enterprise_id, workspace_id)))
        self.assertTrue(revoked.ok)
        self.assertTrue(publisher.closed and viewer.closed)
        self.assertNotIn(device_id, cast_state.rooms_by_id)
        self.assertFalse(devices.heartbeat(DeviceHeartbeatIn(device_key=device_key), request).ok)
        self.assertFalse(jobs.acquire_job(JobAcquireIn(device_key=device_key, worker_id="p55-worker")).ok)
        self.assertFalse(ota.ota_latest(device_key).ok)
        self.assertIsNone(cast._load_device(device_id, self._ctx(enterprise_id, workspace_id)))
        self.assertFalse(devices.register_device(DeviceRegisterIn(device_key=device_key), request).ok)
        with self.assertRaises(HTTPException) as revoked_media:
            tenant_media(media_path, signature=signature, **args)
        self.assertEqual(403, revoked_media.exception.status_code)

    def test_04_quota_reservations_serialize_across_real_sessions(self):
        limits = ((ACTIVE_TASK, 1, 1), (DAILY_SNAPSHOT, 1, 1), (STORAGE_BYTES, 100, 100))
        for metric, limit, amount in limits:
            with get_conn() as conn:
                cur = conn.cursor()
                kwargs = {"active": 10, "daily": 10, "storage": 10000}
                kwargs[{ACTIVE_TASK: "active", DAILY_SNAPSHOT: "daily", STORAGE_BYTES: "storage"}[metric]] = limit
                enterprise_id, workspace_id = self._tenant(cur, **kwargs)
            barrier = threading.Barrier(2)

            def worker(index: int):
                conn = oracledb.connect(dsn=os.environ["T003_ORACLE_DSN"],
                                        user=os.environ["T003_ORACLE_USER"],
                                        password=os.environ["T003_ORACLE_PASSWORD"])
                try:
                    barrier.wait()
                    reserve_and_commit(conn.cursor(), enterprise_id=enterprise_id, workspace_id=workspace_id,
                                       metric=metric, amount=amount, resource_type="gate",
                                       resource_key=f"{metric}-{index}-{uuid.uuid4().hex[:8]}")
                    conn.commit()
                    return "committed"
                except QuotaExceeded:
                    conn.rollback()
                    return "rejected"
                finally:
                    conn.close()

            with ThreadPoolExecutor(max_workers=2) as executor:
                results = sorted(executor.map(worker, (1, 2)))
            self.assertEqual(["committed", "rejected"], results, metric)
            with get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""SELECT USED_VALUE,RESERVED_VALUE FROM SJZQ_QUOTA_USAGE
                    WHERE ENTERPRISE_ID=:e AND METRIC_CODE=:metric AND PERIOD_KEY=:period""",
                            {"e": enterprise_id, "metric": metric, "period": period_key(metric)})
                self.assertEqual((limit, 0), tuple(map(int, cur.fetchone())), metric)
                cur.execute("""SELECT COUNT(*) FROM SJZQ_QUOTA_LEDGER
                    WHERE ENTERPRISE_ID=:e AND METRIC_CODE=:metric""",
                            {"e": enterprise_id, "metric": metric})
                self.assertEqual(2, int(cur.fetchone()[0]), metric)


    def test_05_canonical_task_submission_replays_without_device_or_second_task(self):
        marker = "task-import-" + uuid.uuid4().hex[:12]
        with get_conn() as conn:
            cur = conn.cursor()
            enterprise_id, workspace_id = self._tenant(cur, active=10)
            body = TaskCreateIn.model_validate({
                "submission_id": marker, "source": "excel", "task_name": marker,
                "task_type": "collect", "platform_code": "pinduoduo", "device_id": None,
                "priority": 5, "config": {"max_detail": 5},
                "targets": [{"row_id": "excel:2", "source": "excel", "source_row_index": 2,
                             "keyword": "药品A", "approval": "H1", "name": "药品A",
                             "spec": "10mg", "manufacturer": "厂家A"}],
            })
            context = TenantContext(enterprise_id, workspace_id, 1, 1, "super_admin", frozenset({"task:create"}))
            user = {"user_id": 1, "username": "oracle-gate"}
            first, error = create_canonical_task(cur, body=body, tenant=context, user=user, request=None)
            self.assertIsNone(error)
            replay, error = create_canonical_task(cur, body=body, tenant=context, user=user, request=None)
            self.assertIsNone(error)
            self.assertFalse(first["idempotent"])
            self.assertTrue(replay["idempotent"])
            self.assertEqual(first["task_id"], replay["task_id"])
            changed = TaskCreateIn.model_validate({**body.model_dump(), "priority": 6})
            conflict, error = create_canonical_task(cur, body=changed, tenant=context, user=user, request=None)
            self.assertIsNone(conflict)
            self.assertEqual("IDEMPOTENCY_CONFLICT", error)
            cur.execute("SELECT COUNT(*) FROM SJZQ_TASK WHERE ENTERPRISE_ID=:e AND WORKSPACE_ID=:w AND TASK_NAME=:name",
                        {"e": enterprise_id, "w": workspace_id, "name": marker})
            self.assertEqual(1, int(cur.fetchone()[0]))
            cur.execute("SELECT COUNT(*) FROM SJZQ_COLLECTION_JOB WHERE TASK_ID=:id", {"id": first["task_id"]})
            self.assertEqual(1, int(cur.fetchone()[0]))

            # These are rejected before any Task row can be made, while still
            # using the accepted platform/quota tables in this Oracle session.
            first_target = body.model_dump()["targets"][0]
            duplicate = TaskCreateIn.model_validate({**body.model_dump(), "submission_id": marker + "-duplicate",
                "targets": [first_target, {**first_target, "row_id": "excel:3", "source_row_index": 3}]})
            result, error = create_canonical_task(cur, body=duplicate, tenant=context, user=user, request=None)
            self.assertIsNone(result)
            self.assertEqual("DUPLICATE_TARGET", error)
            disabled = TaskCreateIn.model_validate({**body.model_dump(), "submission_id": marker + "-disabled",
                "platform_code": "tmall", "targets": [{"row_id": "excel:4", "source": "excel",
                    "source_row_index": 4, "platform_code": "tmall", "keyword": "平台关闭目标"}]})
            result, error = create_canonical_task(cur, body=disabled, tenant=context, user=user, request=None)
            self.assertIsNone(result)
            self.assertEqual("PLATFORM_NOT_AVAILABLE", error)
            self._cleanup_task_import_fixture(cur, enterprise_id, workspace_id)
            conn.commit()

        with get_conn() as conn:
            cur = conn.cursor()
            quota_enterprise, quota_workspace = self._tenant(cur, active=0)
            quota_context = TenantContext(quota_enterprise, quota_workspace, 1, 1, "super_admin", frozenset({"task:create"}))
            quota_body = TaskCreateIn.model_validate({**body.model_dump(), "submission_id": marker + "-quota"})
            result, error = create_canonical_task(cur, body=quota_body, tenant=quota_context, user=user, request=None)
            self.assertIsNone(result)
            self.assertEqual("ACTIVE_TASK_QUOTA_EXCEEDED", error)
            self._cleanup_task_import_fixture(cur, quota_enterprise, quota_workspace)
            conn.commit()


    def test_06_canonical_submission_concurrent_replay_is_single_task(self):
        marker = "task-import-race-" + uuid.uuid4().hex[:12]
        with get_conn() as conn:
            enterprise_id, workspace_id = self._tenant(conn.cursor(), active=10)
        barrier = threading.Barrier(2)
        def worker():
            conn = oracledb.connect(dsn=os.environ["T003_ORACLE_DSN"], user=os.environ["T003_ORACLE_USER"], password=os.environ["T003_ORACLE_PASSWORD"])
            try:
                body = TaskCreateIn.model_validate({"submission_id": marker, "source": "manual", "task_name": marker,
                    "task_type": "collect", "platform_code": "pinduoduo", "priority": 5,
                    "targets": [{"row_id": "manual:1", "source": "manual", "source_row_index": 1, "keyword": "并发目标"}]})
                barrier.wait()
                result, error = create_canonical_task(conn.cursor(), body=body,
                    tenant=TenantContext(enterprise_id, workspace_id, 1, 1, "super_admin", frozenset({"task:create"})),
                    user={"user_id": 1, "username": "oracle-gate"}, request=None)
                conn.commit()
                return result, error
            finally:
                conn.close()
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: worker(), range(2)))
        self.assertTrue(all(error is None for _, error in results))
        self.assertEqual([False, True], sorted(result["idempotent"] for result, _ in results))
        self.assertEqual(1, len({result["task_id"] for result, _ in results}))
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM SJZQ_TASK WHERE ENTERPRISE_ID=:e AND WORKSPACE_ID=:w AND TASK_NAME=:name",
                        {"e": enterprise_id, "w": workspace_id, "name": marker})
            self.assertEqual(1, int(cur.fetchone()[0]))
            self._cleanup_task_import_fixture(cur, enterprise_id, workspace_id)
            conn.commit()

    def test_07_task_create_and_quota_lifecycle_cross_sessions_do_not_deadlock(self):
        marker = "task-import-lock-" + uuid.uuid4().hex[:12]
        with get_conn() as conn:
            cur = conn.cursor()
            enterprise_id, workspace_id = self._tenant(cur, active=10)
            held = reserve(cur, enterprise_id=enterprise_id, workspace_id=workspace_id,
                           metric=ACTIVE_TASK, amount=1, resource_type="gate", resource_key=marker)
            conn.commit()
        barrier = threading.Barrier(2)

        def canonical_worker():
            conn = oracledb.connect(dsn=os.environ["T003_ORACLE_DSN"], user=os.environ["T003_ORACLE_USER"], password=os.environ["T003_ORACLE_PASSWORD"])
            try:
                body = TaskCreateIn.model_validate({"submission_id": marker, "source": "manual", "task_name": marker,
                    "task_type": "collect", "platform_code": "pinduoduo", "priority": 5,
                    "targets": [{"row_id": "manual:1", "source": "manual", "source_row_index": 1, "keyword": "锁序目标"}]})
                barrier.wait()
                result, error = create_canonical_task(conn.cursor(), body=body,
                    tenant=TenantContext(enterprise_id, workspace_id, 1, 1, "super_admin", frozenset({"task:create"})),
                    user={"user_id": 1, "username": "oracle-gate"}, request=None)
                conn.commit()
                return "canonical", result, error
            finally:
                conn.close()

        def lifecycle_worker():
            conn = oracledb.connect(dsn=os.environ["T003_ORACLE_DSN"], user=os.environ["T003_ORACLE_USER"], password=os.environ["T003_ORACLE_PASSWORD"])
            try:
                barrier.wait()
                committed = commit(conn.cursor(), held.reservation_id)
                released = release(conn.cursor(), enterprise_id=enterprise_id, metric=ACTIVE_TASK,
                                   resource_type="gate", resource_key=marker)
                conn.commit()
                return "lifecycle", committed.status, released
            finally:
                conn.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = dict((kind, payload) for kind, *payload in executor.map(lambda fn: fn(), (canonical_worker, lifecycle_worker)))
        self.assertIsNone(results["canonical"][1])
        self.assertFalse(results["canonical"][0]["idempotent"])
        self.assertEqual(["committed", True], results["lifecycle"])
        with get_conn() as conn:
            self._cleanup_task_import_fixture(conn.cursor(), enterprise_id, workspace_id)
            conn.commit()

    def test_08_excel_compatibility_route_uses_selected_context_create_and_dispatch(self):
        """The actual compatibility route cannot borrow global/other-tenant dispatch."""
        tag = uuid.uuid4().hex[:12]
        with get_conn() as conn:
            cur = conn.cursor()
            global_role = self._seq(cur, "SJZQ_SEQ_ROLE")
            create_role = self._seq(cur, "SJZQ_SEQ_ROLE")
            combined_role = self._seq(cur, "SJZQ_SEQ_ROLE")
            user_id = self._seq(cur, "SJZQ_SEQ_USER")
            enterprise_a, workspace_a = self._tenant(cur, active=10)
            enterprise_b, workspace_b = self._tenant(cur, active=10)
            for role_id, suffix in ((global_role, "global"), (create_role, "create"), (combined_role, "both")):
                cur.execute("INSERT INTO SJZQ_ROLE (ROLE_ID,ROLE_CODE,ROLE_NAME) VALUES (:id,:code,:name)",
                            {"id": role_id, "code": f"p55-{suffix}-{tag}", "name": f"P55 {suffix} {tag}"})
            for role_id, permission in ((global_role, "task:dispatch"), (create_role, "task:create"),
                                        (combined_role, "task:create"), (combined_role, "task:dispatch")):
                cur.execute("INSERT INTO SJZQ_ROLE_PERM (ROLE_ID,PERM_CODE) VALUES (:role_id,:permission)",
                            {"role_id": role_id, "permission": permission})
            username = f"p55-route-{tag}"
            cur.execute("""INSERT INTO SJZQ_USER (USER_ID,USERNAME,PASSWORD_HASH,ROLE_ID,STATUS)
                           VALUES (:id,:username,'test-only',:role_id,'enabled')""",
                        {"id": user_id, "username": username, "role_id": global_role})
            for enterprise_id, workspace_id, role_id in ((enterprise_a, workspace_a, create_role),
                                                         (enterprise_b, workspace_b, global_role)):
                cur.execute("""INSERT INTO SJZQ_ENTERPRISE_MEMBERSHIP
                    (MEMBERSHIP_ID,ENTERPRISE_ID,USER_ID,ROLE_ID,STATUS)
                    VALUES (:id,:enterprise_id,:user_id,:role_id,'active')""",
                            {"id": self._seq(cur, "SJZQ_SEQ_ENT_MEMBERSHIP"), "enterprise_id": enterprise_id,
                             "user_id": user_id, "role_id": role_id})
                cur.execute("""INSERT INTO SJZQ_WORKSPACE_MEMBERSHIP
                    (ENTERPRISE_ID,WORKSPACE_ID,USER_ID,ROLE_ID)
                    VALUES (:enterprise_id,:workspace_id,:user_id,:role_id)""",
                            {"enterprise_id": enterprise_id, "workspace_id": workspace_id,
                             "user_id": user_id, "role_id": role_id})
            conn.commit()

        route_app = FastAPI()
        route_app.include_router(excel_match.router)
        token = create_token({"user_id": user_id, "username": username, "role_code": f"p55-global-{tag}"})
        body = {"submission_id": f"compat-{tag}", "task_name": f"compat-{tag}", "platform_code": "pinduoduo",
                "rows": [{"row_index": 2, "input_approval_no": "H123", "input_product_name": "路由药品",
                          "input_spec": "10mg", "input_manufacturer": "路由厂家"}]}
        try:
            with TestClient(route_app) as client:
                headers_a = {"Authorization": f"Bearer {token}", "X-Enterprise-Id": str(enterprise_a),
                             "X-Workspace-Id": str(workspace_a)}
                denied = client.post("/api/excel/unmatched-to-task", json=body, headers=headers_a)
                self.assertEqual(403, denied.status_code)  # global dispatch cannot replace selected A dispatch
                headers_b = {"Authorization": f"Bearer {token}", "X-Enterprise-Id": str(enterprise_b),
                             "X-Workspace-Id": str(workspace_b)}
                denied_create = client.post("/api/excel/unmatched-to-task", json=body, headers=headers_b)
                self.assertEqual(403, denied_create.status_code)  # selected B dispatch cannot replace selected create
                with get_conn() as conn:
                    cur = conn.cursor()
                    cur.execute("""UPDATE SJZQ_ENTERPRISE_MEMBERSHIP SET ROLE_ID=:role_id
                                   WHERE ENTERPRISE_ID=:enterprise_id AND USER_ID=:user_id""",
                                {"role_id": combined_role, "enterprise_id": enterprise_a, "user_id": user_id})
                    cur.execute("""UPDATE SJZQ_WORKSPACE_MEMBERSHIP SET ROLE_ID=:role_id
                                   WHERE ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id AND USER_ID=:user_id""",
                                {"role_id": combined_role, "enterprise_id": enterprise_a,
                                 "workspace_id": workspace_a, "user_id": user_id})
                    conn.commit()
                allowed = client.post("/api/excel/unmatched-to-task", json=body, headers=headers_a)
                self.assertEqual(200, allowed.status_code)
                self.assertTrue(allowed.json()["ok"])
            with get_conn() as conn:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM SJZQ_TASK WHERE ENTERPRISE_ID=:e AND WORKSPACE_ID=:w",
                            {"e": enterprise_a, "w": workspace_a})
                self.assertEqual(1, int(cur.fetchone()[0]))
                cur.execute("SELECT COUNT(*) FROM SJZQ_TASK WHERE ENTERPRISE_ID=:e AND WORKSPACE_ID=:w",
                            {"e": enterprise_b, "w": workspace_b})
                self.assertEqual(0, int(cur.fetchone()[0]))
        finally:
            with get_conn() as conn:
                cur = conn.cursor()
                self._cleanup_task_import_fixture(cur, enterprise_a, workspace_a)
                self._cleanup_task_import_fixture(cur, enterprise_b, workspace_b)
                cur.execute("DELETE FROM SJZQ_ROLE_PERM WHERE ROLE_ID IN (:global_role,:create_role,:combined_role)",
                            {"global_role": global_role, "create_role": create_role, "combined_role": combined_role})
                cur.execute("DELETE FROM SJZQ_USER WHERE USER_ID=:user_id", {"user_id": user_id})
                cur.execute("DELETE FROM SJZQ_ROLE WHERE ROLE_ID IN (:global_role,:create_role,:combined_role)",
                            {"global_role": global_role, "create_role": create_role, "combined_role": combined_role})
                for table, predicate, binds in (
                    ("SJZQ_ROLE", "ROLE_ID IN (:global_role,:create_role,:combined_role)", {"global_role": global_role, "create_role": create_role, "combined_role": combined_role}),
                    ("SJZQ_USER", "USER_ID=:user_id", {"user_id": user_id}),
                ):
                    cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {predicate}", binds)
                    self.assertEqual(0, int(cur.fetchone()[0] or 0), table)
                conn.commit()


if __name__ == "__main__":
    unittest.main()
