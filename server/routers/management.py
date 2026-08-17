"""Phase 4 administrator read APIs."""
from __future__ import annotations

from datetime import datetime
from fastapi import APIRouter, Depends, Query

from server.tenant import require_tenant_perms
from server.db import get_conn
from server.schemas import ApiOk
from server import management_queries as queries

router = APIRouter(prefix="/api/management", tags=["management"])


def _run(call):
    with get_conn() as conn:
        return ApiOk(data=call(conn.cursor()))


@router.get("/quarantines")
def quarantines(page:int=Query(1,ge=1),limit:int=Query(50,ge=1,le=200),status:str|None=None,
                start_at:datetime|None=None,end_at:datetime|None=None,failure_reason:str|None=None,
                error_code:str|None=None,platform:str|None=None,product_identity:str|None=None,
                task_id:int|None=None,job_id:int|None=None,parser_version:str|None=None,
                quality_rules_version:str|None=None,tenant=Depends(require_tenant_perms("data:view"))):
    filters=locals(); filters.pop("tenant")
    return _run(lambda cur: queries.list_quarantines(cur,page=page,limit=limit,filters=filters,tenant=tenant))


@router.get("/quarantines/{quarantine_id}")
def get_quarantine(quarantine_id:int,tenant=Depends(require_tenant_perms("data:view"))):
    result=_run(lambda cur: queries.quarantine_detail(cur,quarantine_id,tenant=tenant))
    if result.data is None: return ApiOk(ok=False,message="quarantine not found",data={"error_code":"NOT_FOUND"})
    return result


@router.get("/products/{master_product_id}/snapshots")
def snapshots(master_product_id:int,page:int=Query(1,ge=1),limit:int=Query(50,ge=1,le=200),tenant=Depends(require_tenant_perms("data:view"))):
    return _run(lambda cur: queries.list_snapshots(cur,master_product_id,page=page,limit=limit,tenant=tenant))


@router.get("/quality/metrics")
def metrics(start_at:datetime|None=None,end_at:datetime|None=None,platform:str|None=None,tenant=Depends(require_tenant_perms("data:view"))):
    return _run(lambda cur: queries.quality_metrics(cur,start_at=start_at,end_at=end_at,platform=platform,tenant=tenant))


@router.get("/tasks/{task_id}/trace")
def trace(task_id:int,tenant=Depends(require_tenant_perms("task:view"))):
    result=_run(lambda cur: queries.task_trace(cur,task_id,tenant=tenant))
    if result.data is None: return ApiOk(ok=False,message="task not found",data={"error_code":"NOT_FOUND"})
    return result


@router.get("/tasks/{task_id}/jobs")
def jobs(task_id:int,page:int=Query(1,ge=1),limit:int=Query(50,ge=1,le=200),tenant=Depends(require_tenant_perms("task:view"))):
    return _run(lambda cur: queries.task_jobs(cur,task_id,page,limit,tenant=tenant))


@router.get("/jobs/{job_id}/attempts")
def attempts(job_id:int,page:int=Query(1,ge=1),limit:int=Query(50,ge=1,le=200),tenant=Depends(require_tenant_perms("task:view"))):
    return _run(lambda cur: queries.job_attempts(cur,job_id,page,limit,tenant=tenant))


@router.get("/attempts/{attempt_id}/events")
def attempt_event_list(attempt_id:int,page:int=Query(1,ge=1),limit:int=Query(50,ge=1,le=200),tenant=Depends(require_tenant_perms("task:view"))):
    return _run(lambda cur: queries.attempt_events(cur,attempt_id,page,limit,tenant=tenant))


@router.get("/tasks/{task_id}/events")
def task_event_list(task_id:int,page:int=Query(1,ge=1),limit:int=Query(50,ge=1,le=200),tenant=Depends(require_tenant_perms("task:view"))):
    return _run(lambda cur: queries.task_events(cur,task_id,page,limit,tenant=tenant))
