"""共用业务逻辑。"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Optional

import oracledb

from server.config import settings
from server.db import next_id, row_as_dict, rows_as_dicts


def _ts(v: Any) -> Any:
    if isinstance(v, datetime):
        return v
    return v


def mark_offline_stale(cur: oracledb.Cursor) -> None:
    sec = int(settings.heartbeat_timeout_sec)
    # busy（采集中/投屏）超时同样视为离线
    cur.execute(
        f"""
        UPDATE SJZQ_DEVICE
           SET STATUS = 'offline', UPDATE_TIME = SYSTIMESTAMP
         WHERE STATUS IN ('online', 'busy')
           AND (LAST_HEARTBEAT IS NULL
                OR LAST_HEARTBEAT < SYSTIMESTAMP - NUMTODSINTERVAL(:sec, 'SECOND'))
        """,
        {"sec": sec},
    )
    # 幽灵「采集中」：CURRENT_TASK_ID 指向已结束任务时清空
    cur.execute(
        """
        UPDATE SJZQ_DEVICE d
           SET CURRENT_TASK_ID = NULL,
               STATUS = CASE WHEN NVL(STATUS, 'online') = 'busy' THEN 'online' ELSE STATUS END,
               UPDATE_TIME = SYSTIMESTAMP
         WHERE d.CURRENT_TASK_ID IS NOT NULL
           AND NOT EXISTS (
                 SELECT 1 FROM SJZQ_TASK t
                  WHERE t.TASK_ID = d.CURRENT_TASK_ID
                    AND t.STATUS = 'running'
               )
        """
    )


def device_online_flag(last_heartbeat: Any, status: str) -> bool:
    """在线判定：心跳未超时，且状态不是 offline/error。busy 也算在线。"""
    st = (status or "").lower()
    if st in ("offline", "error", ""):
        # 空状态仍看心跳
        if st in ("offline", "error"):
            return False
    if last_heartbeat is None:
        return False
    if not isinstance(last_heartbeat, datetime):
        return False
    # 放宽时钟偏差：用本地时间比较时多给 60 秒余量
    grace = int(settings.heartbeat_timeout_sec) + 60
    hb = last_heartbeat.replace(tzinfo=None) if last_heartbeat.tzinfo else last_heartbeat
    return hb >= datetime.now() - timedelta(seconds=grace)


def get_device_by_key(cur: oracledb.Cursor, device_key: str) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT DEVICE_ID, DEVICE_KEY, DEVICE_NAME, PLATFORM_CODE, APP_VERSION,
               OS_VERSION, MODEL, STATUS, LAST_IP, LAST_HEARTBEAT,
               CURRENT_TASK_ID, NVL(KEYWORD_RUN_COUNT, 0) AS KEYWORD_RUN_COUNT,
               OWNER_USER_ID, GROUP_NAME, RUN_STATE, RUN_STARTED_AT, REST_UNTIL,
               NVL(MAX_CONTINUOUS_MIN, 120) AS MAX_CONTINUOUS_MIN,
               NVL(MIN_REST_MIN, 30) AS MIN_REST_MIN,
               CREATE_TIME, UPDATE_TIME
          FROM SJZQ_DEVICE
         WHERE DEVICE_KEY = :k
        """,
        {"k": device_key},
    )
    return row_as_dict(cur)


def enrich_device(d: dict[str, Any]) -> dict[str, Any]:
    d = dict(d)
    d["online"] = device_online_flag(d.get("last_heartbeat"), d.get("status") or "")
    return d


def clob_to_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, str):
        return v
    try:
        return v.read()
    except Exception:
        return str(v)


def parse_json_obj(text: Optional[str]) -> dict[str, Any]:
    if not text:
        return {}
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def list_platforms(cur: oracledb.Cursor, enabled_only: bool = False) -> list[dict[str, Any]]:
    sql = """
        SELECT PLATFORM_CODE, PLATFORM_NAME, ENABLED, SORT_NO, REMARK
          FROM SJZQ_PLATFORM
    """
    if enabled_only:
        sql += " WHERE ENABLED = 1"
    sql += " ORDER BY SORT_NO, PLATFORM_CODE"
    cur.execute(sql)
    return rows_as_dicts(cur)


def append_task_log(
    cur: oracledb.Cursor,
    task_id: int,
    message: str,
    device_id: Optional[int] = None,
    level: str = "info",
) -> None:
    log_id = next_id(cur, "SJZQ_SEQ_TASK_LOG")
    cur.execute(
        """
        INSERT INTO SJZQ_TASK_LOG (LOG_ID, TASK_ID, DEVICE_ID, LEVEL_CODE, MESSAGE)
        VALUES (:id, :tid, :did, :lv, :msg)
        """,
        {
            "id": log_id,
            "tid": task_id,
            "did": device_id,
            "lv": (level or "info")[:16],
            "msg": (message or "")[:2000],
        },
    )
