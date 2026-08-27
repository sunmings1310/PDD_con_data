export const CLIENT_ERROR_CODES = Object.freeze({
  UNAUTHORIZED: 'UNAUTHORIZED',
  FORBIDDEN: 'FORBIDDEN',
  NOT_FOUND: 'NOT_FOUND',
  CONTEXT_STALE: 'CONTEXT_STALE',
  REQUEST_CANCELLED: 'REQUEST_CANCELLED',
  UNEXPECTED_RESPONSE: 'UNEXPECTED_RESPONSE',
  REQUEST_FAILED: 'REQUEST_FAILED',
})

const NOT_FOUND_MESSAGE = '资源不存在或不属于当前租户'
const CANONICAL_NOT_FOUND_DATA = Object.freeze({
  ok: false,
  message: NOT_FOUND_MESSAGE,
  data: Object.freeze({ error_code: CLIENT_ERROR_CODES.NOT_FOUND }),
})

function errorCode(payload, status) {
  if (status === 401) return CLIENT_ERROR_CODES.UNAUTHORIZED
  if (status === 403) return CLIENT_ERROR_CODES.FORBIDDEN
  if (status === 404) return CLIENT_ERROR_CODES.NOT_FOUND
  const code = payload?.data?.error_code || payload?.error_code
  if (code) return String(code)
  return CLIENT_ERROR_CODES.REQUEST_FAILED
}

function errorMessage(payload, status, fallback = '请求失败') {
  const code = errorCode(payload, status)
  if (status === 404 || code === CLIENT_ERROR_CODES.NOT_FOUND) return NOT_FOUND_MESSAGE
  const detail = payload?.detail
  if (typeof detail === 'string') return detail
  if (typeof payload?.message === 'string' && payload.message) return payload.message
  return fallback
}

function errorData(payload, status, code) {
  if (status === 404 || code === CLIENT_ERROR_CODES.NOT_FOUND) return CANONICAL_NOT_FOUND_DATA
  return payload
}

export class ClientRequestError extends Error {
  constructor(message, { status = 0, code = CLIENT_ERROR_CODES.REQUEST_FAILED, data = null, cause = null } = {}) {
    super(message, cause ? { cause } : undefined)
    this.name = 'ClientRequestError'
    this.status = Number(status || 0)
    this.code = code
    this.data = data
    this.response = this.status ? { status: this.status, data } : undefined
  }
}

export function staleContextError(cause = null) {
  return new ClientRequestError('请求上下文已切换', {
    code: CLIENT_ERROR_CODES.CONTEXT_STALE,
    cause,
  })
}

export function apiEnvelopeError(payload, status = 200) {
  if (!payload || payload.ok !== false) return null
  const code = errorCode(payload, status)
  return new ClientRequestError(errorMessage(payload, status), {
    status,
    code,
    data: errorData(payload, status, code),
  })
}

export async function parseJsonBlob(blob) {
  if (!blob || typeof blob.text !== 'function') return null
  try {
    return JSON.parse(await blob.text())
  } catch {
    return null
  }
}

export function blobResponseError(payload, status = 200) {
  return apiEnvelopeError(payload, status) || new ClientRequestError('下载接口未返回文件', {
    status,
    code: CLIENT_ERROR_CODES.UNEXPECTED_RESPONSE,
    data: payload,
  })
}

export async function normalizeHttpError(error) {
  if (error instanceof ClientRequestError) return error
  const status = Number(error?.response?.status || 0)
  let payload = error?.response?.data || null
  if (payload && typeof payload.text === 'function') {
    payload = await parseJsonBlob(payload) || payload
  }
  const code = errorCode(payload, status)
  return new ClientRequestError(errorMessage(payload, status, error?.message || '网络异常'), {
    status,
    code,
    data: errorData(payload, status, code),
    cause: error,
  })
}

export function shouldNotify(error) {
  return ![
    CLIENT_ERROR_CODES.CONTEXT_STALE,
    CLIENT_ERROR_CODES.REQUEST_CANCELLED,
  ].includes(error?.code)
}
