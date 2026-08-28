const MAX_TEXT = 512

export function normalizeText(value) {
  return String(value ?? '').trim().replace(/\s+/g, ' ')
}

export function normalizedPlatformProductId(value) {
  const raw = normalizeText(value)
  if (!raw) return ''
  try {
    const url = new URL(raw)
    return normalizeText(url.searchParams.get('goods_id') || url.searchParams.get('goodsId') || url.searchParams.get('item_id'))
  } catch {
    return ''
  }
}

function drugKey(platformCode, row) {
  const approval = normalizeText(row.approval || row.input_approval_no)
  const name = normalizeText(row.name || row.input_product_name)
  const spec = normalizeText(row.spec || row.input_spec)
  const manufacturer = normalizeText(row.manufacturer || row.input_manufacturer)
  return approval && name && spec && manufacturer
    ? `${platformCode}|drug|${approval.toUpperCase()}|${name.toUpperCase()}|${spec.toUpperCase()}|${manufacturer.toUpperCase()}`
    : ''
}

export function stableDedupKey(platformCode, row) {
  const productId = normalizeText(row.platform_product_id || row.goods_id || normalizedPlatformProductId(row.raw_value || row.keyword))
  if (productId) return `${platformCode}|product|${productId}`
  const medicine = drugKey(platformCode, row)
  if (medicine) return medicine
  const keyword = normalizeText(row.keyword || row.raw_value || row.search_keyword)
  return keyword ? `${platformCode}|keyword|${keyword.toUpperCase()}` : ''
}

function rowBase({ source, sourceRowIndex, rawValue, platformCode, ...row }) {
  const keyword = normalizeText(row.keyword || row.search_keyword || row.input_product_name || rawValue)
  const approval = normalizeText(row.approval || row.input_approval_no)
  const name = normalizeText(row.name || row.input_product_name)
  const spec = normalizeText(row.spec || row.input_spec)
  const manufacturer = normalizeText(row.manufacturer || row.input_manufacturer)
  const platformProductId = normalizeText(row.platform_product_id || row.goods_id)
  return {
    row_id: row.row_id || `${source}:${sourceRowIndex}`,
    source,
    source_row_index: sourceRowIndex,
    raw_value: rawValue || '',
    normalized_value: keyword,
    platform_code: platformCode,
    platform_product_id: platformProductId || undefined,
    keyword: keyword.slice(0, 256),
    approval: approval.slice(0, 128),
    name: name.slice(0, MAX_TEXT),
    spec: spec.slice(0, 256),
    manufacturer: manufacturer.slice(0, 256),
    original_row: row.original_row || undefined,
    candidate: row.candidate || null,
    candidates: row.candidates || [],
    validation_status: 'valid',
    match_status: 'not_applicable',
    selection_status: 'selected',
    dispatch_status: 'ready',
    error_codes: [],
    source_row_ids: [row.row_id || `${source}:${sourceRowIndex}`],
  }
}

export function normalizeManualRows(text, platformCode) {
  return String(text || '').split(/\r?\n/).map((rawValue, index) => {
    const row = rowBase({ source: 'manual', sourceRowIndex: index + 1, rawValue, platformCode })
    if (!row.keyword) {
      row.validation_status = 'invalid'
      row.selection_status = 'excluded'
      row.dispatch_status = 'blocked'
      row.error_codes.push('EMPTY_INPUT')
    }
    return row
  }).filter((row) => row.raw_value || row.error_codes.length)
}

export function normalizeExcelRows(rows, platformCode) {
  return (rows || []).map((sourceRow, index) => {
    const sourceRowIndex = Number(sourceRow.row_index ?? index + 1)
    const row = rowBase({
      ...sourceRow,
      source: 'excel',
      sourceRowIndex,
      rawValue: sourceRow.search_keyword || sourceRow.input_product_name || '',
      platformCode,
    })
    const hasTargetFields = Boolean(row.platform_product_id || (row.approval && row.name && row.spec && row.manufacturer))
    if (!hasTargetFields) {
      row.validation_status = 'invalid'
      row.dispatch_status = 'blocked'
      row.error_codes.push('MISSING_REQUIRED_TARGET_FIELDS')
    }
    if (sourceRow.selected_candidate) {
      row.match_status = 'matched'
      row.candidate = sourceRow.selected_candidate
      row.platform_product_id = normalizeText(sourceRow.selected_candidate.goods_id || sourceRow.selected_candidate.platform_product_id) || row.platform_product_id
    } else if (sourceRow.match_status === 'unique') {
      row.match_status = 'matched'
      row.candidate = sourceRow
    } else if (sourceRow.match_status === 'multiple') {
      row.match_status = 'multiple'
      row.selection_status = 'choice_required'
      row.dispatch_status = 'blocked'
      row.error_codes.push('CANDIDATE_CHOICE_REQUIRED')
    } else {
      row.match_status = 'unmatched'
    }
    if (row.validation_status === 'invalid') row.dispatch_status = 'blocked'
    return row
  })
}

export function chooseCandidate(rows, rowId, candidate) {
  return rows.map((row) => row.row_id !== rowId ? row : {
    ...row,
    candidate,
    platform_product_id: normalizeText(candidate?.goods_id || candidate?.platform_product_id) || row.platform_product_id,
    match_status: 'matched',
    selection_status: 'selected',
    dispatch_status: row.validation_status === 'valid' ? 'ready' : 'blocked',
    error_codes: row.error_codes.filter((code) => code !== 'CANDIDATE_CHOICE_REQUIRED'),
  })
}

export function setRowSelection(rows, rowId, selected) {
  return rows.map((row) => row.row_id !== rowId ? row : {
    ...row,
    selection_status: selected ? 'selected' : 'excluded',
    dispatch_status: selected && row.validation_status === 'valid' && row.match_status !== 'multiple' ? 'ready' : 'blocked',
  })
}

export function deduplicateRows(rows, platformCode) {
  const firstByKey = new Map()
  return rows.map((row) => {
    const key = stableDedupKey(platformCode, row)
    if (!key) return row
    const first = firstByKey.get(key)
    if (!first) {
      firstByKey.set(key, row)
      return { ...row, dedup_key: key }
    }
    first.source_row_ids.push(...row.source_row_ids)
    return {
      ...row,
      dedup_key: key,
      selection_status: 'excluded',
      dispatch_status: 'blocked',
      error_codes: [...row.error_codes, 'DUPLICATE_DRAFT_INPUT'],
      duplicate_of: first.row_id,
    }
  })
}

export function prepareDraftRows(rows, platformCode) {
  return deduplicateRows(rows, platformCode)
}

export function reviewDraft(rows) {
  const result = { total: rows.length, ready: 0, invalid: 0, duplicate: 0, excluded: 0, choice_required: 0, blocked: 0 }
  for (const row of rows) {
    if (row.validation_status === 'invalid') result.invalid += 1
    if (row.error_codes.includes('DUPLICATE_DRAFT_INPUT')) result.duplicate += 1
    if (row.selection_status === 'excluded') result.excluded += 1
    if (row.selection_status === 'choice_required') result.choice_required += 1
    if (row.dispatch_status === 'ready' && row.selection_status === 'selected') result.ready += 1
    if (row.dispatch_status === 'blocked') result.blocked += 1
  }
  return result
}

export function newSubmissionId() {
  return globalThis.crypto?.randomUUID?.() || `submission-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export function buildCanonicalPayload({ submissionId, source, task, rows }) {
  const review = reviewDraft(rows)
  if (!submissionId || !review.ready || review.invalid || review.choice_required) {
    throw new Error('TASK_DRAFT_NOT_SUBMITTABLE')
  }
  const targets = rows
    .filter((row) => row.selection_status === 'selected' && row.dispatch_status === 'ready')
    .map((row) => ({
      row_id: row.row_id,
      source: row.source,
      source_row_index: row.source_row_index,
      platform_code: row.platform_code,
      platform_product_id: row.platform_product_id || null,
      keyword: row.keyword,
      approval: row.approval || null,
      name: row.name || null,
      spec: row.spec || null,
      manufacturer: row.manufacturer || null,
      original_row: row.original_row || null,
      provenance_row_ids: row.source_row_ids,
    }))
  return {
    submission_id: submissionId,
    source,
    task_name: task.task_name,
    task_type: task.task_type,
    platform_code: task.platform_code,
    device_id: task.device_id,
    priority: task.priority,
    config: task.config,
    targets,
  }
}

