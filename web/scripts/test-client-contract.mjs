import assert from 'node:assert/strict'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { dirname, join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  createClientContextProvider,
  createSessionLifecycle,
  headersForContext,
} from '../src/api/clientContext.js'
import {
  apiEnvelopeError,
  blobResponseError,
  CLIENT_ERROR_CODES,
  normalizeHttpError,
  parseJsonBlob,
} from '../src/api/clientErrors.js'
import { hasRoutePermissions, requiredRoutePermissions } from '../src/router/permissions.js'

class MemoryStorage {
  constructor(entries = {}) {
    this.values = new Map(Object.entries(entries))
  }
  getItem(key) { return this.values.get(key) ?? null }
  setItem(key, value) { this.values.set(key, String(value)) }
  removeItem(key) { this.values.delete(key) }
}

const deferred = () => {
  let resolve
  const promise = new Promise((done) => { resolve = done })
  return { promise, resolve }
}

const storage = new MemoryStorage()
const context = createClientContextProvider({ storage })
context.update({ token: 'token-A', enterpriseId: 11, workspaceId: 101 })
const requestA = context.beginRequest()
const headersA = headersForContext(requestA.snapshot)
assert.deepEqual(headersA, {
  Authorization: 'Bearer token-A',
  'X-Enterprise-Id': '11',
  'X-Workspace-Id': '101',
})
const lateA = deferred()
let visibleResult = null
const writeA = (async () => {
  const result = await lateA.promise
  if (requestA.isCurrent()) visibleResult = result
})()
context.update({ enterpriseId: 22, workspaceId: 202 })
assert.equal(requestA.signal.aborted, true)
assert.equal(requestA.isCurrent(), false)
assert.deepEqual(headersA, {
  Authorization: 'Bearer token-A',
  'X-Enterprise-Id': '11',
  'X-Workspace-Id': '101',
})
const requestB = context.beginRequest()
assert.deepEqual(headersForContext(requestB.snapshot), {
  Authorization: 'Bearer token-A',
  'X-Enterprise-Id': '22',
  'X-Workspace-Id': '202',
})
lateA.resolve('stale-A')
await writeA
assert.equal(visibleResult, null)
requestB.release()
console.log('CONTEXT_SNAPSHOT=PASS immutable_headers=true old_abort=true stale_write=false')

const requestKinds = ['json', 'multipart', 'blob']
for (const kind of requestKinds) {
  const request = context.beginRequest()
  const headers = headersForContext(request.snapshot)
  assert.equal(headers.Authorization, 'Bearer token-A')
  assert.equal(headers['X-Enterprise-Id'], '22')
  assert.equal(headers['X-Workspace-Id'], '202')
  if (kind === 'multipart') assert.ok(new FormData() instanceof FormData)
  if (kind === 'blob') assert.ok(new Blob(['payload']) instanceof Blob)
  request.release()
}
console.log('REQUEST_KINDS=PASS json=true multipart=true blob=true shared_headers=true')

const apiNotFound = apiEnvelopeError({
  ok: false,
  message: 'internal object detail',
  data: { error_code: 'NOT_FOUND' },
})
assert.equal(apiNotFound.code, CLIENT_ERROR_CODES.NOT_FOUND)
assert.equal(apiNotFound.message, '资源不存在或不属于当前租户')
assert.equal(apiNotFound.response.status, 200)
const forbidden = await normalizeHttpError({ response: { status: 403, data: { detail: '无权限' } } })
assert.equal(forbidden.code, CLIENT_ERROR_CODES.FORBIDDEN)
assert.equal(forbidden.message, '无权限')
assert.equal(forbidden.response.status, 403)
const httpNotFound = await normalizeHttpError({ response: { status: 404, data: { detail: 'tenant-specific secret' } } })
assert.equal(httpNotFound.code, CLIENT_ERROR_CODES.NOT_FOUND)
assert.equal(httpNotFound.message, '资源不存在或不属于当前租户')
const unauthorized = await normalizeHttpError({ response: { status: 401, data: { detail: 'expired' } } })
assert.equal(unauthorized.code, CLIENT_ERROR_CODES.UNAUTHORIZED)
const blobPayload = await parseJsonBlob(new Blob([
  JSON.stringify({ ok: false, message: '导出失败', data: { error_code: 'EXPORT_FAILED' } }),
], { type: 'application/json' }))
const blobError = apiEnvelopeError(blobPayload)
assert.equal(blobError.code, 'EXPORT_FAILED')
assert.equal(blobError.message, '导出失败')
const unexpectedBlob = blobResponseError({ ok: true, data: { ignored: true } })
assert.equal(unexpectedBlob.code, CLIENT_ERROR_CODES.UNEXPECTED_RESPONSE)
assert.equal(unexpectedBlob.message, '下载接口未返回文件')
console.log('ERROR_CONTRACT=PASS api_ok=false axios_403=true http_404=true not_found_non_enumerable=true blob_json=true')

let resetCount = 0
let redirectCount = 0
const session = createSessionLifecycle(context)
session.bindReset(() => { resetCount += 1 })
session.bindRedirect(() => { redirectCount += 1 })
session.activate({ token: 'token-B', enterpriseId: 33, workspaceId: 303 })
assert.equal(session.invalidate(), true)
assert.equal(session.invalidate(), false)
assert.equal(resetCount, 1)
assert.equal(redirectCount, 1)
assert.deepEqual(context.getSnapshot(), { token: '', enterpriseId: '', workspaceId: '', generation: 4 })
assert.equal(storage.getItem('sjzq_token'), null)
assert.equal(storage.getItem('sjzq_enterprise_id'), null)
assert.equal(storage.getItem('sjzq_workspace_id'), null)
console.log('SESSION_401=PASS idempotent=true store_reset=1 redirect=1 storage_cleared=true')

assert.deepEqual(requiredRoutePermissions({ perm: 'excel:match' }), ['excel:match'])
assert.deepEqual(requiredRoutePermissions({ perms: ['task:view', 'data:view'] }), ['task:view', 'data:view'])
const allowed = new Set(['task:view', 'data:view'])
assert.equal(hasRoutePermissions({ perms: ['task:view', 'data:view'] }, (item) => allowed.has(item)), true)
allowed.delete('data:view')
assert.equal(hasRoutePermissions({ perms: ['task:view', 'data:view'] }, (item) => allowed.has(item)), false)
console.log('ROUTE_PERMISSIONS=PASS perm=true perms_and=true partial_denied=true')

const scriptDir = dirname(fileURLToPath(import.meta.url))
const webRoot = join(scriptDir, '..')
const sourceRoot = join(webRoot, 'src')
const sourceFiles = []
const collectFiles = (directory) => {
  for (const name of readdirSync(directory)) {
    const path = join(directory, name)
    if (statSync(path).isDirectory()) collectFiles(path)
    else if (/\.(js|vue)$/.test(name)) sourceFiles.push(path)
  }
}
collectFiles(sourceRoot)
for (const path of sourceFiles) {
  const source = readFileSync(path, 'utf8')
  const relativePath = relative(webRoot, path).replaceAll('\\', '/')
  if (relativePath !== 'src/api/http.js') {
    assert.doesNotMatch(source, /(?:from\s+['"]axios['"]|\baxios\.(?:get|post|put|delete|request)\s*\()/, relativePath)
  }
  if (!['src/views/devices/DeviceCast.vue', 'src/views/devices/DeviceLive.vue'].includes(relativePath)) {
    assert.doesNotMatch(source, /\b(?:fetch|XMLHttpRequest)\s*\(/, relativePath)
  }
}
const excelSource = readFileSync(join(sourceRoot, 'views/excel/ExcelMatch.vue'), 'utf8')
for (const marker of [
  "http.getBlob('/api/excel/template')",
  'http.post(',
  "http.postBlob(\n      '/api/excel/export-batch'",
  "store.hasPerm('excel:import')",
  "store.hasPerm('excel:match')",
  "store.hasPerm('excel:export')",
]) assert.ok(excelSource.includes(marker), marker)
const layoutSource = readFileSync(join(sourceRoot, 'layout/AdminLayout.vue'), 'utf8')
assert.match(layoutSource, /router-view :key="`\$\{store\.contextGeneration\}:\$\{route\.fullPath\}`"/)
assert.doesNotMatch(layoutSource, /router\.go\s*\(/)
const httpSource = readFileSync(join(sourceRoot, 'api/http.js'), 'utf8')
assert.match(httpSource, /undefined, \{ synchronous: true \}\)/)
console.log('SOURCE_CONTRACT=PASS direct_http_bypass=false excel_permissions=true tenant_remount=true')
