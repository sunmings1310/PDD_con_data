"""Explicit Enterprise/Workspace request context and tenant-scoped RBAC."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import Depends, HTTPException, Request

from server.db import get_conn, row_as_dict, rows_as_dicts


@dataclass(frozen=True)
class TenantContext:
    enterprise_id: int
    workspace_id: int
    user_id: int
    role_id: int
    role_code: str
    perms: frozenset[str]

    @property
    def binds(self) -> dict[str, int]:
        return {"enterprise_id": self.enterprise_id, "workspace_id": self.workspace_id}


def _header_id(request: Request, name: str) -> int:
    raw = (request.headers.get(name) or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail=f"缺少 {name} 租户上下文")
    try:
        value = int(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"无效 {name}") from exc
    if value <= 0:
        raise HTTPException(status_code=400, detail=f"无效 {name}")
    return value


def load_context(request: Request, user: dict[str, Any]) -> TenantContext:
    enterprise_id = _header_id(request, "X-Enterprise-Id")
    workspace_id = _header_id(request, "X-Workspace-Id")
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT m.ROLE_ID,r.ROLE_CODE
                 FROM SJZQ_ENTERPRISE_MEMBERSHIP m
                 JOIN SJZQ_ROLE r ON r.ROLE_ID=m.ROLE_ID
                 JOIN SJZQ_ENTERPRISE e ON e.ENTERPRISE_ID=m.ENTERPRISE_ID AND e.STATUS='active'
                 JOIN SJZQ_WORKSPACE w ON w.ENTERPRISE_ID=m.ENTERPRISE_ID
                                      AND w.WORKSPACE_ID=:workspace_id AND w.STATUS='active'
                WHERE m.ENTERPRISE_ID=:enterprise_id AND m.USER_ID=:user_id AND m.STATUS='active'
                  AND (NOT EXISTS (SELECT 1 FROM SJZQ_WORKSPACE_MEMBERSHIP x
                                    WHERE x.WORKSPACE_ID=w.WORKSPACE_ID)
                       OR EXISTS (SELECT 1 FROM SJZQ_WORKSPACE_MEMBERSHIP x
                                   WHERE x.ENTERPRISE_ID=m.ENTERPRISE_ID
                                     AND x.WORKSPACE_ID=w.WORKSPACE_ID AND x.USER_ID=m.USER_ID))""",
            {"enterprise_id": enterprise_id, "workspace_id": workspace_id, "user_id": int(user["user_id"])},
        )
        membership = row_as_dict(cur)
        if not membership:
            # Do not disclose whether the enterprise, workspace or membership exists.
            raise HTTPException(status_code=404, detail="租户资源不存在")
        role_id = int(membership["role_id"])
        cur.execute("SELECT PERM_CODE FROM SJZQ_ROLE_PERM WHERE ROLE_ID=:role_id", {"role_id": role_id})
        perms = frozenset(str(row[0]) for row in cur.fetchall())
    return TenantContext(enterprise_id, workspace_id, int(user["user_id"]), role_id,
                         str(membership["role_code"]), perms)


def require_tenant_perms(*needed: str):
    from server.auth_util import get_current_user

    async def dependency(request: Request, user: dict = Depends(get_current_user)) -> TenantContext:
        context = load_context(request, user)
        if not all(code in context.perms for code in needed):
            raise HTTPException(status_code=403, detail="无权限")
        request.state.tenant = context
        return context

    return dependency


def list_user_contexts(cur: Any, user_id: int) -> list[dict[str, Any]]:
    cur.execute(
        """SELECT e.ENTERPRISE_ID,e.ENTERPRISE_CODE,e.ENTERPRISE_NAME,
                  w.WORKSPACE_ID,w.WORKSPACE_CODE,w.WORKSPACE_NAME,r.ROLE_CODE,r.ROLE_NAME
             FROM SJZQ_ENTERPRISE_MEMBERSHIP m
             JOIN SJZQ_ENTERPRISE e ON e.ENTERPRISE_ID=m.ENTERPRISE_ID AND e.STATUS='active'
             JOIN SJZQ_WORKSPACE w ON w.ENTERPRISE_ID=e.ENTERPRISE_ID AND w.STATUS='active'
             JOIN SJZQ_ROLE r ON r.ROLE_ID=m.ROLE_ID
            WHERE m.USER_ID=:user_id AND m.STATUS='active'
              AND (NOT EXISTS (SELECT 1 FROM SJZQ_WORKSPACE_MEMBERSHIP x WHERE x.WORKSPACE_ID=w.WORKSPACE_ID)
                   OR EXISTS (SELECT 1 FROM SJZQ_WORKSPACE_MEMBERSHIP x
                               WHERE x.WORKSPACE_ID=w.WORKSPACE_ID AND x.USER_ID=m.USER_ID))
            ORDER BY e.ENTERPRISE_NAME,w.WORKSPACE_NAME""",
        {"user_id": user_id},
    )
    return rows_as_dicts(cur)


def tenant_predicate(alias: str = "") -> str:
    prefix = f"{alias}." if alias else ""
    return f"{prefix}ENTERPRISE_ID=:enterprise_id AND {prefix}WORKSPACE_ID=:workspace_id"
