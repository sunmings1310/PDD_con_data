import {
  blobResponseError,
  CLIENT_ERROR_CODES,
  ClientRequestError,
  parseJsonBlob,
} from './clientErrors.js'

const FILE_CONTRACTS = Object.freeze({
  xlsx: Object.freeze({
    extensions: Object.freeze(['.xlsx']),
    contentTypes: Object.freeze([
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    ]),
  }),
  zip: Object.freeze({
    extensions: Object.freeze(['.zip']),
    contentTypes: Object.freeze(['application/zip', 'application/x-zip-compressed']),
  }),
})

function responseHeader(headers, name) {
  return String(headers?.get?.(name) || headers?.[name] || '')
}

function unexpectedFileResponse(status, data = null) {
  return new ClientRequestError('下载接口未返回可信文件', {
    status,
    code: CLIENT_ERROR_CODES.UNEXPECTED_RESPONSE,
    data,
  })
}

async function recognizableJson(blob) {
  if (!blob || typeof blob.text !== 'function') return null
  const prefix = (await blob.slice(0, Math.min(blob.size, 1024)).text()).trimStart()
  if (!prefix.startsWith('{') && !prefix.startsWith('[')) return null
  const payload = await parseJsonBlob(blob)
  return payload === null ? Object.freeze({ malformed_json: true }) : payload
}

function dispositionHasAllowedExtension(disposition, extensions) {
  if (!/\battachment\b/i.test(disposition)) return false
  const match = disposition.match(/filename\*\s*=\s*(?:UTF-8'')?([^;]+)/i)
    || disposition.match(/filename\s*=\s*([^;]+)/i)
  if (!match) return false
  let filename = match[1].trim().replace(/^['"]|['"]$/g, '')
  try { filename = decodeURIComponent(filename) } catch { /* use the literal filename */ }
  const normalized = filename.toLowerCase()
  return extensions.some((extension) => normalized.endsWith(extension.toLowerCase()))
}

export async function fileResponseError(response, contractName) {
  const contract = FILE_CONTRACTS[contractName]
  if (!contract) return unexpectedFileResponse(response?.status)
  const blob = response?.data
  if (!blob || typeof blob.text !== 'function' || typeof blob.slice !== 'function') {
    return unexpectedFileResponse(response?.status, blob)
  }

  const contentType = responseHeader(response.headers, 'content-type').split(';', 1)[0].trim().toLowerCase()
  const disposition = responseHeader(response.headers, 'content-disposition')
  const jsonPayload = await recognizableJson(blob)
  if (jsonPayload !== null) return blobResponseError(jsonPayload, response.status)

  if (!contentType
      || contentType.startsWith('text/')
      || contentType.includes('json')
      || contentType.includes('html')) {
    return unexpectedFileResponse(response.status)
  }
  if (contract.contentTypes.includes(contentType)) return null
  if (contentType === 'application/octet-stream'
      && dispositionHasAllowedExtension(disposition, contract.extensions)) {
    return null
  }
  return unexpectedFileResponse(response.status)
}
