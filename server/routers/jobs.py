"""Phase 2 worker-facing CollectionJob protocol endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from server.auth_util import require_perms
from server.tenant import require_tenant_perms
from server.db import get_conn
from server.job_state import JobStateConflict
from server.job_service import JobProtocolError, acquire, checkpoint, complete, error_data, fail, heartbeat, pause_task, recoverable_work, resume_task, start, yield_paused
from server.schemas import ApiOk, JobAcquireIn, JobCheckpointIn, JobCompleteIn, JobFailIn, JobHeartbeatIn, JobLeaseIn, JobRecoverIn
from server.services import get_device_by_key
from server.job_reconciliation import reconcile_oracle

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _device(cur, device_key: str):
    device = get_device_by_key(cur, device_key)
    if not device:
        raise JobProtocolError("DEVICE_NOT_FOUND", "device not registered")
    return int(device["device_id"])


def _result(call):
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            return ApiOk(data=call(cur))
    except (JobProtocolError, JobStateConflict) as exc:
        return ApiOk(ok=False, message=str(exc), data=error_data(exc))


def _owned_task(cur, task_id: int, tenant):
    cur.execute("""SELECT 1 FROM SJZQ_TASK WHERE TASK_ID=:task_id
                    AND ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id""",
                {"task_id": task_id, **tenant.binds})
    if not cur.fetchone():
        raise JobProtocolError("TASK_NOT_FOUND", "task does not exist")


@router.post("/acquire")
def acquire_job(body: JobAcquireIn):
    def run(cur):
        did = _device(cur, body.device_key)
        value = acquire(cur, device_id=did, worker_id=body.worker_id, platform_code=body.platform_code, lease_seconds=body.lease_seconds)
        return value
    return _result(run)


@router.post("/start")
def start_job(body: JobLeaseIn):
    return _result(lambda cur: start(cur, device_id=_device(cur, body.device_key), job_id=body.job_id, attempt_id=body.attempt_id, worker_id=body.worker_id, lease_token=body.lease_token))


@router.post("/heartbeat")
def job_heartbeat(body: JobHeartbeatIn):
    return _result(lambda cur: heartbeat(cur, device_id=_device(cur, body.device_key), job_id=body.job_id, attempt_id=body.attempt_id, worker_id=body.worker_id, lease_token=body.lease_token, lease_seconds=body.lease_seconds))


@router.post("/checkpoint")
def job_checkpoint(body: JobCheckpointIn):
    return _result(lambda cur: checkpoint(cur, device_id=_device(cur, body.device_key), job_id=body.job_id, attempt_id=body.attempt_id, worker_id=body.worker_id, lease_token=body.lease_token, version=body.version, idempotency_key=body.idempotency_key, payload=body.payload))


@router.post("/complete")
def complete_job(body: JobCompleteIn):
    return _result(lambda cur: complete(cur, device_id=_device(cur, body.device_key), job_id=body.job_id, attempt_id=body.attempt_id, worker_id=body.worker_id, lease_token=body.lease_token, result_receipt_key=body.result_receipt_key, result_receipt_keys=body.result_receipt_keys, result_product_id=body.result_product_id))


@router.post("/fail")
def fail_job(body: JobFailIn):
    return _result(lambda cur: fail(cur, device_id=_device(cur, body.device_key), job_id=body.job_id, attempt_id=body.attempt_id, worker_id=body.worker_id, lease_token=body.lease_token, error_class=body.error_class, error_code=body.error_code, error_message=body.error_message))


@router.post("/yield")
def yield_job(body: JobLeaseIn):
    return _result(
        lambda cur: yield_paused(
            cur,
            device_id=_device(cur, body.device_key),
            job_id=body.job_id,
            attempt_id=body.attempt_id,
            worker_id=body.worker_id,
            lease_token=body.lease_token,
        )
    )


@router.post("/recover")
def recover_jobs(body: JobRecoverIn):
    return _result(lambda cur: recoverable_work(cur, device_id=_device(cur, body.device_key), worker_id=body.worker_id))


@router.post("/tasks/{task_id}/pause")
def pause_jobs(task_id: int, tenant=Depends(require_tenant_perms("task:create"))):
    def run(cur):
        _owned_task(cur, task_id, tenant)
        return {"task_id": task_id, "paused_jobs": pause_task(cur, task_id=task_id)}
    return _result(run)


@router.post("/tasks/{task_id}/resume")
def resume_jobs(task_id: int, tenant=Depends(require_tenant_perms("task:create"))):
    def run(cur):
        _owned_task(cur, task_id, tenant)
        return {"task_id": task_id, "resumed_jobs": resume_task(cur, task_id=task_id)}
    return _result(run)


@router.post("/reconcile")
def reconcile_jobs(limit: int = 100, user=Depends(require_perms("task:create"))):
    del user
    bounded = max(1, min(int(limit), 1000))
    return _result(
        lambda cur: {
            "limit": bounded,
            "report": {
                "scanned": (report := reconcile_oracle(cur, limit=bounded)).scanned,
                "repaired": report.repaired,
                "actions": [action.__dict__ for action in report.actions],
            },
        }
    )
