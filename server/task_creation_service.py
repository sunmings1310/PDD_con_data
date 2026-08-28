"""Canonical Task creation transaction shared by manual and Excel surfaces."""
from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from server.db import next_id
from server.job_service import create_jobs_for_task
from server.platforms import TASK_COLLECT, TASK_NURTURE
from server.quota import ACTIVE_TASK, QuotaExceeded, lock_metric_scope, reserve_and_commit
from server.services import append_task_log, clob_to_str


def _text(value: Any, limit: int) -> str:
    return str(value or '').strip()[:limit]


def _payload_hash(body: Any, targets: list[dict[str, Any]]) -> str:
    payload = {
        'source': body.source, 'task_name': body.task_name, 'task_type': body.task_type,
        'platform_code': body.platform_code, 'priority': body.priority, 'device_id': body.device_id,
        'config': {key: value for key, value in (body.config or {}).items() if key != '_submission'}, 'targets': targets,
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _targets(body: Any) -> tuple[list[dict[str, Any]], str | None]:
    result: list[dict[str, Any]] = []
    raw_targets = [(item.model_dump() if hasattr(item, 'model_dump') else item.dict()) for item in body.targets] if body.targets else [
        {'row_id': f'legacy:{index}', 'source': body.source, 'source_row_index': index,
         'keyword': keyword} for index, keyword in enumerate(body.keywords)
    ]
    seen: set[str] = set()
    for raw in raw_targets:
        platform = _text(raw.get('platform_code') or body.platform_code, 32)
        if platform != body.platform_code:
            return [], 'TARGET_PLATFORM_MISMATCH'
        keyword = _text(raw.get('keyword'), 256)
        product_id = _text(raw.get('platform_product_id'), 128)
        approval, name = _text(raw.get('approval'), 128), _text(raw.get('name'), 512)
        spec, manufacturer = _text(raw.get('spec'), 256), _text(raw.get('manufacturer'), 256)
        if not (product_id or keyword or (approval and name and spec and manufacturer)):
            return [], 'INVALID_TARGET'
        row_id = _text(raw.get('row_id'), 128)
        if not row_id or row_id in seen:
            return [], 'DUPLICATE_ROW_ID'
        seen.add(row_id)
        result.append({'row_id': row_id, 'source': _text(raw.get('source'), 32),
            'source_row_index': int(raw.get('source_row_index') or 0), 'platform_product_id': product_id,
            'keyword': keyword or name or approval, 'approval': approval, 'name': name, 'spec': spec,
            'manufacturer': manufacturer, 'original_row': raw.get('original_row'),
            'provenance_row_ids': raw.get('provenance_row_ids') or [row_id]})
    return result, None if result else 'EMPTY_TARGETS'


def _find_submission(cur: Any, tenant: Any, submission_id: str) -> tuple[int, str] | None:
    cur.execute("""SELECT TASK_ID, JSON_VALUE(CONFIG_JSON, '$._submission.payload_sha256' RETURNING VARCHAR2(64))
                    FROM SJZQ_TASK
                   WHERE ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id
                     AND JSON_VALUE(CONFIG_JSON, '$._submission.id' RETURNING VARCHAR2(128))=:submission_id
                   FOR UPDATE""", {**tenant.binds, 'submission_id': submission_id})
    row = cur.fetchone()
    return (int(row[0]), str(row[1] or '')) if row else None


def create_canonical_task(cur: Any, *, body: Any, tenant: Any, user: dict, request: Any) -> tuple[dict[str, Any] | None, str | None]:
    if body.task_type not in (TASK_COLLECT, TASK_NURTURE): return None, 'UNSUPPORTED_TASK_TYPE'
    targets, error = _targets(body)
    if error: return None, error
    if not _text(body.task_name, 128): return None, 'INVALID_TASK_NAME'
    submission_id = _text(body.submission_id, 128) or f'legacy-{uuid.uuid4().hex}'
    payload_sha256 = _payload_hash(body, targets)
    lock_metric_scope(cur, enterprise_id=tenant.enterprise_id, metric=ACTIVE_TASK)
    prior = _find_submission(cur, tenant, submission_id)
    if prior:
        if prior[1] != payload_sha256: return None, 'IDEMPOTENCY_CONFLICT'
        return {'task_id': prior[0], 'idempotent': True, 'submission_id': submission_id}, None
    if body.device_id is not None:
        cur.execute("""SELECT PLATFORM_CODE,OWNER_USER_ID FROM SJZQ_DEVICE WHERE DEVICE_ID=:id
                       AND ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id AND REVOKED_AT IS NULL""",
                    {'id': body.device_id, **tenant.binds})
        device = cur.fetchone()
        if not device: return None, 'NOT_FOUND'
        if _text(device[0], 32) != body.platform_code: return None, 'DEVICE_PLATFORM_MISMATCH'
        if tenant.role_code != 'super_admin' and int(device[1] or 0) != int(user['user_id']): return None, 'NOT_FOUND'
    config = {key: value for key, value in (body.config or {}).items() if key != '_submission'}
    account_id = config.get('account_id')
    if account_id is not None:
        cur.execute("""SELECT PLATFORM_CODE,OWNER_USER_ID FROM SJZQ_PLATFORM_ACCOUNT WHERE ACCOUNT_ID=:id
                       AND ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id""", {'id': account_id, **tenant.binds})
        account = cur.fetchone()
        if not account or _text(account[0], 32) != body.platform_code or (tenant.role_code != 'super_admin' and int(account[1] or 0) != int(user['user_id'])): return None, 'NOT_FOUND'
    task_id = next_id(cur, 'SJZQ_SEQ_TASK')
    try:
        reserve_and_commit(cur, enterprise_id=tenant.enterprise_id, workspace_id=tenant.workspace_id,
                           metric=ACTIVE_TASK, amount=1, resource_type='task', resource_key=str(task_id))
    except QuotaExceeded as exc:
        return None, str(exc)
    config['_submission'] = {'id': submission_id, 'payload_sha256': payload_sha256, 'source': body.source, 'acknowledged': True}
    cur.execute("""INSERT INTO SJZQ_TASK (TASK_ID,TASK_NAME,TASK_TYPE,PLATFORM_CODE,STATUS,PRIORITY,DEVICE_ID,
                   KEYWORD_TEXT,TARGET_COUNT,CONFIG_JSON,REVIEW_STATUS,CREATE_USER_ID,CREATE_USERNAME,ENTERPRISE_ID,WORKSPACE_ID)
                   VALUES (:task_id,:task_name,:task_type,:platform,'pending',:priority,:device_id,:keywords,:target_count,
                   :config,'pending',:user_id,:username,:enterprise_id,:workspace_id)""",
                {'task_id': task_id, 'task_name': _text(body.task_name, 128), 'task_type': body.task_type,
                 'platform': body.platform_code, 'priority': body.priority, 'device_id': body.device_id,
                 'keywords': '\n'.join(target['keyword'] for target in targets), 'target_count': len(targets),
                 'config': json.dumps(config, ensure_ascii=False, sort_keys=True), 'user_id': user['user_id'],
                 'username': user['username'], **tenant.binds})
    for index, target in enumerate(targets):
        cur.execute("""INSERT INTO SJZQ_TASK_ITEM (ITEM_ID,TASK_ID,ROW_INDEX,KEYWORD,TARGET_SPEC,TARGET_APPROVAL,TARGET_NAME,
                       TARGET_MANUFACTURER,ORIGINAL_ROW_JSON,STATUS,ENTERPRISE_ID,WORKSPACE_ID)
                       VALUES (:item_id,:task_id,:row_index,:keyword,:spec,:approval,:name,:manufacturer,:original,'pending',:enterprise_id,:workspace_id)""",
                    {'item_id': next_id(cur, 'SJZQ_SEQ_TASK_ITEM'), 'task_id': task_id, 'row_index': index,
                     'keyword': target['keyword'], 'spec': target['spec'] or None, 'approval': target['approval'] or None,
                     'name': target['name'] or None, 'manufacturer': target['manufacturer'] or None,
                     'original': json.dumps({'row_id': target['row_id'], 'source': target['source'], 'source_row_index': target['source_row_index'], 'original_row': target['original_row'], 'provenance_row_ids': target['provenance_row_ids']}, ensure_ascii=False), **tenant.binds})
    if body.task_type == TASK_COLLECT: create_jobs_for_task(cur, task_id=task_id)
    append_task_log(cur, task_id, f'任务已创建，目标 {len(targets)} 个')
    return {'task_id': task_id, 'idempotent': False, 'submission_id': submission_id}, None
