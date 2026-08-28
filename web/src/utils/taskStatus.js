export const TASK_STATUS_LABELS = Object.freeze({
  pending: '待执行',
  running: '执行中',
  succeeded: '全部完成',
  partially_succeeded: '部分成功',
  done: '全部完成',
  failed: '执行失败',
  cancelled: '已取消',
  timed_out: '执行超时',
})

export const TASK_STATUS_TYPES = Object.freeze({
  pending: 'info', running: 'warning', succeeded: 'success', partially_succeeded: 'warning',
  done: 'success', failed: 'danger', cancelled: 'info', timed_out: 'danger',
})

export function taskStatusText(status, fallback) {
  const raw = status || fallback
  return TASK_STATUS_LABELS[status] || TASK_STATUS_LABELS[fallback] || `未知状态（${raw || '-'}）`
}

export function taskStatusType(status) {
  return TASK_STATUS_TYPES[status] || 'info'
}

export function viewScope(...values) {
  return values.map((value) => String(value ?? '')).join('|')
}
