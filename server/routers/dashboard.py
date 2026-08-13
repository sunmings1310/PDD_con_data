"""顶部状态栏统计。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from server.auth_util import get_current_user
from server.config import settings
from server.db import get_conn
from server.schemas import ApiOk
from server.services import mark_offline_stale

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary")
def summary(_=Depends(get_current_user)):
    with get_conn() as conn:
        cur = conn.cursor()
        mark_offline_stale(cur)
        cur.execute(
            f"""
            SELECT COUNT(*) FROM SJZQ_DEVICE
             WHERE NVL(STATUS, 'offline') NOT IN ('offline', 'error')
               AND LAST_HEARTBEAT IS NOT NULL
               AND LAST_HEARTBEAT >= SYSTIMESTAMP - NUMTODSINTERVAL({int(settings.heartbeat_timeout_sec) + 60}, 'SECOND')
            """
        )
        online = int(cur.fetchone()[0])
        cur.execute("SELECT COUNT(*) FROM SJZQ_TASK WHERE STATUS = 'running'")
        running = int(cur.fetchone()[0])
        cur.execute("SELECT COUNT(*) FROM SJZQ_TASK WHERE STATUS = 'pending'")
        pending = int(cur.fetchone()[0])
        cur.execute("SELECT COUNT(*) FROM SJZQ_PRODUCT")
        products = int(cur.fetchone()[0])
        return ApiOk(
            data={
                "online_devices": online,
                "running_tasks": running,
                "pending_tasks": pending,
                "product_count": products,
            }
        )
