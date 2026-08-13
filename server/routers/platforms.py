"""平台字典。"""

from __future__ import annotations

from fastapi import APIRouter

from server.db import get_conn
from server.schemas import ApiOk
from server.services import list_platforms

router = APIRouter(prefix="/api/platforms", tags=["platforms"])


@router.get("")
def get_platforms(enabled_only: bool = False):
    with get_conn() as conn:
        cur = conn.cursor()
        return ApiOk(data=list_platforms(cur, enabled_only=enabled_only))
