import axios from 'axios'
import { ElMessage } from 'element-plus'
import { clientContext, headersForContext, invalidateClientSession } from './clientContext.js'
import {
  apiEnvelopeError,
  blobResponseError,
  CLIENT_ERROR_CODES,
  normalizeHttpError,
  parseJsonBlob,
  shouldNotify,
  staleContextError,
} from './clientErrors.js'
import { fileResponseError } from './clientFiles.js'

const http = axios.create({
  baseURL: '/',
  timeout: 60000,
})

let notifyError = (message) => ElMessage.error(message)

export function setHttpErrorNotifier(notifier) {
  notifyError = typeof notifier === 'function' ? notifier : (message) => ElMessage.error(message)
}

http.interceptors.request.use((config) => {
  const requestContext = clientContext.beginRequest()
  config.__clientContextRequest = requestContext
  for (const [name, value] of Object.entries(headersForContext(requestContext.snapshot))) {
    if (typeof config.headers?.set === 'function') config.headers.set(name, value)
    else {
      config.headers ||= {}
      config.headers[name] = value
    }
  }
  if (config.signal && typeof AbortSignal.any === 'function') {
    config.signal = AbortSignal.any([config.signal, requestContext.signal])
  } else {
    config.signal = requestContext.signal
  }
  return config
}, undefined, { synchronous: true })

http.interceptors.response.use(
  async (res) => {
    const requestContext = res.config.__clientContextRequest
    const data = res.data
    let envelopeError = null
    if (res.config.__fileContract) {
      envelopeError = await fileResponseError(res, res.config.__fileContract)
    } else if (data && typeof data.text === 'function') {
      const contentType = String(res.headers?.get?.('content-type') || res.headers?.['content-type'] || data.type || '')
      if (contentType.includes('json')) {
        const payload = await parseJsonBlob(data)
        envelopeError = blobResponseError(payload, res.status)
      }
    } else {
      envelopeError = apiEnvelopeError(data, res.status)
    }
    if (requestContext && !requestContext.isCurrent()) {
      requestContext.release()
      return Promise.reject(staleContextError())
    }
    requestContext?.release()
    if (envelopeError) {
      if (shouldNotify(envelopeError)) notifyError(envelopeError.message)
      return Promise.reject(envelopeError)
    }
    return res.config.__returnRawResponse ? res : data
  },
  async (err) => {
    const requestContext = err.config?.__clientContextRequest
    const initiallyStale = requestContext && !requestContext.isCurrent()
    let normalized = initiallyStale
      ? staleContextError(err)
      : await normalizeHttpError(err)
    if (requestContext && !requestContext.isCurrent()) normalized = staleContextError(err)
    requestContext?.release()
    if (normalized.status === 401) {
      invalidateClientSession()
    }
    if (normalized.code === CLIENT_ERROR_CODES.REQUEST_FAILED && axios.isCancel(err)) {
      normalized.code = CLIENT_ERROR_CODES.REQUEST_CANCELLED
    }
    if (shouldNotify(normalized)) notifyError(normalized.message)
    return Promise.reject(normalized)
  },
)

http.getBlob = async (url, config = {}) => {
  const { expectedFile, ...requestConfig } = config
  const response = await http.get(url, {
    ...requestConfig,
    responseType: 'blob',
    __returnRawResponse: true,
    __fileContract: expectedFile || '__missing__',
  })
  return response.data
}

http.postBlob = async (url, data, config = {}) => {
  const { expectedFile, ...requestConfig } = config
  const response = await http.post(url, data, {
    ...requestConfig,
    responseType: 'blob',
    __returnRawResponse: true,
    __fileContract: expectedFile || '__missing__',
  })
  return response.data
}

export default http
