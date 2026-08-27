import axios from 'axios'
import { ElMessage } from 'element-plus'
import { clientContext, headersForContext, invalidateClientSession } from './clientContext.js'
import {
  apiEnvelopeError,
  CLIENT_ERROR_CODES,
  normalizeHttpError,
  parseJsonBlob,
  shouldNotify,
  staleContextError,
} from './clientErrors.js'

const http = axios.create({
  baseURL: '/',
  timeout: 60000,
})

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
})

http.interceptors.response.use(
  async (res) => {
    const requestContext = res.config.__clientContextRequest
    const data = res.data
    let envelopeError = null
    if (data && typeof data.text === 'function') {
      const contentType = String(res.headers?.['content-type'] || data.type || '')
      if (contentType.includes('json')) {
        const payload = await parseJsonBlob(data)
        envelopeError = apiEnvelopeError(payload, res.status)
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
      if (shouldNotify(envelopeError)) ElMessage.error(envelopeError.message)
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
    if (shouldNotify(normalized)) ElMessage.error(normalized.message)
    return Promise.reject(normalized)
  },
)

http.getBlob = async (url, config = {}) => {
  const response = await http.get(url, { ...config, responseType: 'blob', __returnRawResponse: true })
  return response.data
}

http.postBlob = async (url, data, config = {}) => {
  const response = await http.post(url, data, { ...config, responseType: 'blob', __returnRawResponse: true })
  return response.data
}

export default http
