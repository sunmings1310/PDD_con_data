"""Enterprise/workspace administration and quota visibility."""

from fastapi import APIRouter, Depends, HTTPException, Request

from server.auth_util import get_current_user, require_perms
from server.db import get_conn, row_as_dict, rows_as_dicts
from server.tenant import list_user_contexts, require_tenant_perms

router = APIRouter(prefix="/api/enterprises", tags=["enterprises"])


@router.get("/contexts")
def contexts(user=Depends(get_current_user)):
    with get_conn() as conn:
        return {"items": list_user_contexts(conn.cursor(), int(user["user_id"]))}


@router.post("")
def create_enterprise(body: dict, user=Depends(require_perms("system:config"))):
    code = str(body.get("enterprise_code") or "").strip()
    name = str(body.get("enterprise_name") or "").strip()
    if not code or not name:
        raise HTTPException(status_code=400, detail="企业编码和名称必填")
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT SJZQ_SEQ_ENTERPRISE.NEXTVAL FROM DUAL"); enterprise_id = int(cur.fetchone()[0])
        cur.execute("SELECT SJZQ_SEQ_WORKSPACE.NEXTVAL FROM DUAL"); workspace_id = int(cur.fetchone()[0])
        cur.execute("""INSERT INTO SJZQ_ENTERPRISE
            (ENTERPRISE_ID,ENTERPRISE_CODE,ENTERPRISE_NAME) VALUES (:id,:code,:name)""",
            {"id": enterprise_id, "code": code, "name": name})
        cur.execute("""INSERT INTO SJZQ_WORKSPACE
            (WORKSPACE_ID,ENTERPRISE_ID,WORKSPACE_CODE,WORKSPACE_NAME)
            VALUES (:wid,:eid,'default','Default Workspace')""", {"wid": workspace_id, "eid": enterprise_id})
        cur.execute("INSERT INTO SJZQ_ENTERPRISE_QUOTA (ENTERPRISE_ID) VALUES (:id)", {"id": enterprise_id})
        cur.execute("SELECT SJZQ_SEQ_ENT_MEMBERSHIP.NEXTVAL FROM DUAL"); membership_id = int(cur.fetchone()[0])
        cur.execute("""INSERT INTO SJZQ_ENTERPRISE_MEMBERSHIP
            (MEMBERSHIP_ID,ENTERPRISE_ID,USER_ID,ROLE_ID) VALUES (:mid,:eid,:uid,:rid)""",
            {"mid": membership_id, "eid": enterprise_id, "uid": int(user["user_id"]), "rid": int(user["role_id"])})
        conn.commit()
    return {"enterprise_id": enterprise_id, "workspace_id": workspace_id}


@router.get("/current")
def current(context=Depends(require_tenant_perms("data:view"))):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT e.ENTERPRISE_ID,e.ENTERPRISE_CODE,e.ENTERPRISE_NAME,e.STATUS,e.RETENTION_DAYS,
                              w.WORKSPACE_ID,w.WORKSPACE_CODE,w.WORKSPACE_NAME,w.STATUS WORKSPACE_STATUS,
                              q.MAX_WORKSPACES,q.MAX_USERS,q.MAX_ACTIVE_TASKS,q.MAX_DAILY_SNAPSHOTS,q.STORAGE_BYTES
                         FROM SJZQ_ENTERPRISE e JOIN SJZQ_WORKSPACE w ON w.ENTERPRISE_ID=e.ENTERPRISE_ID
                         JOIN SJZQ_ENTERPRISE_QUOTA q ON q.ENTERPRISE_ID=e.ENTERPRISE_ID
                        WHERE e.ENTERPRISE_ID=:enterprise_id AND w.WORKSPACE_ID=:workspace_id""", context.binds)
        value = row_as_dict(cur)
        if not value: raise HTTPException(status_code=404, detail="租户资源不存在")
        return value


@router.get("/current/members")
def members(context=Depends(require_tenant_perms("user:manage"))):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT m.MEMBERSHIP_ID,m.USER_ID,u.USERNAME,u.REAL_NAME,m.ROLE_ID,r.ROLE_CODE,r.ROLE_NAME,m.STATUS
                         FROM SJZQ_ENTERPRISE_MEMBERSHIP m JOIN SJZQ_USER u ON u.USER_ID=m.USER_ID
                         JOIN SJZQ_ROLE r ON r.ROLE_ID=m.ROLE_ID
                        WHERE m.ENTERPRISE_ID=:enterprise_id ORDER BY u.USERNAME""",
                    {"enterprise_id": context.enterprise_id})
        return {"items": rows_as_dicts(cur)}


@router.post("/current/workspaces")
def create_workspace(body: dict, context=Depends(require_tenant_perms("system:config"))):
    code = str(body.get("workspace_code") or "").strip(); name = str(body.get("workspace_name") or "").strip()
    if not code or not name: raise HTTPException(status_code=400, detail="Workspace 编码和名称必填")
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT COUNT(*),MAX(q.MAX_WORKSPACES) FROM SJZQ_WORKSPACE w
                         JOIN SJZQ_ENTERPRISE_QUOTA q ON q.ENTERPRISE_ID=w.ENTERPRISE_ID
                        WHERE w.ENTERPRISE_ID=:enterprise_id AND w.STATUS='active'""",
                    {"enterprise_id": context.enterprise_id})
        count, maximum = cur.fetchone()
        if int(count) >= int(maximum): raise HTTPException(status_code=409, detail="WORKSPACE_QUOTA_EXCEEDED")
        cur.execute("SELECT SJZQ_SEQ_WORKSPACE.NEXTVAL FROM DUAL"); workspace_id = int(cur.fetchone()[0])
        cur.execute("""INSERT INTO SJZQ_WORKSPACE
            (WORKSPACE_ID,ENTERPRISE_ID,WORKSPACE_CODE,WORKSPACE_NAME)
            VALUES (:wid,:eid,:code,:name)""", {"wid":workspace_id,"eid":context.enterprise_id,"code":code,"name":name})
        conn.commit()
        return {"workspace_id": workspace_id}


@router.get("/current/quota-usage")
def quota_usage(context=Depends(require_tenant_perms("system:config"))):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT METRIC_CODE,PERIOD_KEY,USED_VALUE,RESERVED_VALUE,VERSION_NO,UPDATE_TIME
                         FROM SJZQ_QUOTA_USAGE WHERE ENTERPRISE_ID=:enterprise_id
                         ORDER BY METRIC_CODE,PERIOD_KEY DESC""",
                    {"enterprise_id": context.enterprise_id})
        usage = rows_as_dicts(cur)
        cur.execute("""SELECT RESERVATION_ID,WORKSPACE_ID,METRIC_CODE,PERIOD_KEY,AMOUNT,
                              RESOURCE_TYPE,RESOURCE_KEY,STATUS,EXPIRES_AT,CREATE_TIME
                         FROM SJZQ_QUOTA_RESERVATION WHERE ENTERPRISE_ID=:enterprise_id
                           AND WORKSPACE_ID=:workspace_id AND STATUS='held'
                         ORDER BY CREATE_TIME DESC FETCH FIRST 100 ROWS ONLY""", context.binds)
        return {"usage": usage, "active_reservations": rows_as_dicts(cur)}
