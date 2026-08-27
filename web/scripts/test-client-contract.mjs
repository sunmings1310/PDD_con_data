import assert from 'node:assert/strict'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { dirname, join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import { AxiosError, AxiosHeaders, CanceledError } from 'axios'
import http, { setHttpErrorNotifier } from '../src/api/http.js'
import {
  activateClientSession,
  bindSessionReset,
  bindUnauthorizedRedirect,
  getClientContext,
  updateClientContext,
} from '../src/api/clientContext.js'
import { CLIENT_ERROR_CODES } from '../src/api/clientErrors.js'
import { hasRoutePermissions, requiredRoutePermissions } from '../src/router/permissions.js'
import { permissionsForTenant } from '../src/stores/tenantPermissions.js'

const notices = []
setHttpErrorNotifier((message) => notices.push(message))

function response(config, data, status = 200, headers = {}) {
  return {
    data,
    status,
    statusText: String(status),
    headers: new AxiosHeaders(headers),
    config,
    request: {},
  }
}

function resolvedAdapter(data, { status = 200, headers = {}, inspect = () => {} } = {}) {
  return async (config) => {
    inspect(config)
    return response(config, data, status, headers)
  }
}

function rejectedAdapter(status, data, { inspect = () => {}, headers = {} } = {}) {
  return async (config) => {
    inspect(config)
    const res = response(config, data, status, headers)
    throw new AxiosError(`HTTP ${status}`, AxiosError.ERR_BAD_RESPONSE, config, {}, res)
  }
}

function deferredAdapter() {
  let seenConfig = null
  let settleResolve = null
  let settleReject = null
  const adapter = (config) => {
    seenConfig = config
    return new Promise((resolve, reject) => {
      settleResolve = resolve
      settleReject = reject
      const cancel = () => reject(new CanceledError('canceled', config, {}))
      if (config.signal?.aborted) cancel()
      else config.signal?.addEventListener('abort', cancel, { once: true })
    })
  }
  return {
    adapter,
    config: () => seenConfig,
    resolve(data, status = 200, headers = {}) {
      settleResolve(response(seenConfig, data, status, headers))
    },
    rejectStatus(status, data) {
      const res = response(seenConfig, data, status)
      settleReject(new AxiosError(`HTTP ${status}`, AxiosError.ERR_BAD_RESPONSE, seenConfig, {}, res))
    },
  }
}

function requestHeaders(config) {
  return {
    Authorization: config.headers.get('Authorization'),
    enterprise: config.headers.get('X-Enterprise-Id'),
    workspace: config.headers.get('X-Workspace-Id'),
  }
}

async function capturedError(promise) {
  try {
    await promise
  } catch (error) {
    return error
  }
  assert.fail('request unexpectedly resolved')
}

const contexts = [
  { enterprise_id: 11, workspace_id: 101, perms: ['data:view'] },
  { enterprise_id: 22, workspace_id: 202, perms: ['task:view', 'task:create'] },
]
assert.deepEqual(permissionsForTenant(contexts, 11, 101), ['data:view'])
assert.deepEqual(permissionsForTenant(contexts, 22, 202), ['task:view', 'task:create'])
assert.deepEqual(permissionsForTenant(contexts, 99, 999), [])
console.log('TENANT_CONTEXT_LIST_HAS_PERMS=PASS A=data:view B=task:view,task:create')
console.log('FETCHME_SELECTS_CONTEXT_PERMS=PASS unknown_context=empty no_global_fallback=true')

activateClientSession({ token: 'token-A', enterpriseId: 11, workspaceId: 101 })
const observedKinds = []
const json = await http.post('/contract/json', { value: 1 }, {
  adapter: resolvedAdapter({ ok: true, data: { kind: 'json' } }, {
    inspect(config) {
      observedKinds.push(['json', requestHeaders(config)])
    },
  }),
})
assert.equal(json.data.kind, 'json')
const form = new FormData()
form.append('file', new Blob(['sheet']), 'sample.xlsx')
const multipart = await http.post('/contract/multipart', form, {
  adapter: resolvedAdapter({ ok: true, data: { kind: 'multipart' } }, {
    inspect(config) {
      assert.ok(config.data instanceof FormData)
      observedKinds.push(['multipart', requestHeaders(config)])
    },
  }),
})
assert.equal(multipart.data.kind, 'multipart')
for (const [, headers] of observedKinds) {
  assert.deepEqual(headers, { Authorization: 'Bearer token-A', enterprise: '11', workspace: '101' })
}
console.log('HTTP_REAL_INSTANCE=PASS imported=http.js adapter=deterministic json=true multipart=true')

const deferredA = deferredAdapter()
const requestA = http.get('/contract/deferred-A', { adapter: deferredA.adapter })
assert.deepEqual(requestHeaders(deferredA.config()), {
  Authorization: 'Bearer token-A', enterprise: '11', workspace: '101',
})
updateClientContext({ enterpriseId: 22, workspaceId: 202 })
const staleA = await capturedError(requestA)
assert.equal(staleA.code, CLIENT_ERROR_CODES.CONTEXT_STALE)
let requestBHeaders = null
await http.get('/contract/B', {
  adapter: resolvedAdapter({ ok: true, data: { winner: 'B' } }, {
    inspect(config) { requestBHeaders = requestHeaders(config) },
  }),
})
assert.deepEqual(requestBHeaders, {
  Authorization: 'Bearer token-A', enterprise: '22', workspace: '202',
})
console.log('CONTEXT_A_TO_B=PASS A_aborted=true A_stale=true B_headers=22/202')

const callerController = new AbortController()
const callerDeferred = deferredAdapter()
const callerRequest = http.get('/contract/caller-cancel', {
  adapter: callerDeferred.adapter,
  signal: callerController.signal,
})
callerController.abort()
const callerError = await capturedError(callerRequest)
assert.equal(callerError.code, CLIENT_ERROR_CODES.REQUEST_CANCELLED)
assert.equal(getClientContext().enterpriseId, '22')
console.log('CALLER_CANCELLATION=PASS code=REQUEST_CANCELLED context_current=true')

async function statusError(status, payload) {
  return capturedError(http.get(`/contract/status-${status}`, {
    adapter: rejectedAdapter(status, payload),
  }))
}

const conflict403 = await statusError(403, {
  detail: '无权限', data: { error_code: 'NOT_FOUND' },
})
assert.equal(conflict403.code, CLIENT_ERROR_CODES.FORBIDDEN)
const conflict404 = await statusError(404, {
  detail: 'tenant resource exists', data: { error_code: 'FORBIDDEN', secret: 'hidden' },
})
assert.equal(conflict404.code, CLIENT_ERROR_CODES.NOT_FOUND)
assert.deepEqual(conflict404.data, {
  ok: false,
  message: '资源不存在或不属于当前租户',
  data: { error_code: 'NOT_FOUND' },
})
assert.doesNotMatch(JSON.stringify(conflict404.data), /exists|hidden|FORBIDDEN/)
const businessNotFound = await capturedError(http.get('/contract/business-not-found', {
  adapter: resolvedAdapter({
    ok: false,
    message: 'internal detail',
    data: { error_code: 'NOT_FOUND', secret: 'hidden' },
  }),
}))
assert.equal(businessNotFound.code, CLIENT_ERROR_CODES.NOT_FOUND)
assert.deepEqual(businessNotFound.data, conflict404.data)
console.log('ERROR_PRECEDENCE=PASS status403=FORBIDDEN status404=NOT_FOUND business_not_found=sanitized')
console.log('ERROR_PRECEDENCE_EXIT=0')

let resetCount = 0
let redirectCount = 0
bindSessionReset(() => { resetCount += 1 })
bindUnauthorizedRedirect(() => { redirectCount += 1 })
activateClientSession({ token: 'token-401', enterpriseId: 22, workspaceId: 202 })
const conflict401 = await Promise.allSettled([
  http.get('/contract/401-A', {
    adapter: rejectedAdapter(401, { data: { error_code: 'FORBIDDEN' } }),
  }),
  http.get('/contract/401-B', {
    adapter: rejectedAdapter(401, { data: { error_code: 'NOT_FOUND' } }),
  }),
])
assert.equal(conflict401[0].status, 'rejected')
assert.equal(conflict401[0].reason.code, CLIENT_ERROR_CODES.UNAUTHORIZED)
assert.equal(conflict401[1].status, 'rejected')
assert.ok([
  CLIENT_ERROR_CODES.UNAUTHORIZED,
  CLIENT_ERROR_CODES.CONTEXT_STALE,
].includes(conflict401[1].reason.code))
assert.equal(resetCount, 1)
assert.equal(redirectCount, 1)
assert.equal(getClientContext().token, '')
console.log('CONCURRENT_401=PASS reset=1 redirect=1 conflicting_payload_cannot_override=true')

activateClientSession({ token: 'token-files', enterpriseId: 22, workspaceId: 202 })
const xlsxBytes = new Uint8Array([0x50, 0x4b, 0x03, 0x04, 0x58, 0x4c, 0x53, 0x58])
const zipBytes = new Uint8Array([0x50, 0x4b, 0x03, 0x04, 0x5a, 0x49, 0x50])
const xlsx = await http.getBlob('/api/excel/template', {
  expectedFile: 'xlsx',
  adapter: resolvedAdapter(new Blob([xlsxBytes]), {
    headers: {
      'content-type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      'content-disposition': 'attachment; filename=goods_library_match_template.xlsx',
    },
  }),
})
assert.equal(xlsx.size, xlsxBytes.length)
const zip = await http.postBlob('/api/excel/export-batch', { rows: [] }, {
  expectedFile: 'zip',
  adapter: resolvedAdapter(new Blob([zipBytes]), {
    headers: {
      'content-type': 'application/zip',
      'content-disposition': "attachment; filename*=UTF-8''products.zip",
    },
  }),
})
assert.equal(zip.size, zipBytes.length)
const octetXlsx = await http.getBlob('/api/excel/template', {
  expectedFile: 'xlsx',
  adapter: resolvedAdapter(new Blob([xlsxBytes]), {
    headers: {
      'content-type': 'application/octet-stream',
      'content-disposition': 'attachment; filename=template.xlsx',
    },
  }),
})
assert.equal(octetXlsx.size, xlsxBytes.length)
console.log('BLOB_VALID_FILES=PASS template=xlsx export=zip trusted_octet_stream=true')

const fakeFiles = [
  ['text/plain', new Blob(['not a workbook']), { 'content-type': 'text/plain' }],
  ['text/html', new Blob(['<html>login</html>']), { 'content-type': 'text/html' }],
  ['octet/no-disposition', new Blob([xlsxBytes]), { 'content-type': 'application/octet-stream' }],
  ['json/spoofed-mime', new Blob([JSON.stringify({ ok: true, data: { not: 'a file' } })]), {
    'content-type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'content-disposition': 'attachment; filename=fake.xlsx',
  }],
]
for (const [name, blob, headers] of fakeFiles) {
  const error = await capturedError(http.getBlob('/api/excel/template', {
    expectedFile: 'xlsx', adapter: resolvedAdapter(blob, { headers }),
  }))
  assert.equal(error.code, CLIENT_ERROR_CODES.UNEXPECTED_RESPONSE, name)
}
const missingContract = await capturedError(http.getBlob('/api/excel/template', {
  adapter: resolvedAdapter(new Blob([xlsxBytes]), {
    headers: { 'content-type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' },
  }),
}))
assert.equal(missingContract.code, CLIENT_ERROR_CODES.UNEXPECTED_RESPONSE)
console.log('BLOB_NON_FILE=PASS outcome=REJECTED text_plain=true text_html=true octet_untrusted=true json_spoof=true')

assert.deepEqual(requiredRoutePermissions({ perm: 'excel:match' }), ['excel:match'])
assert.deepEqual(requiredRoutePermissions({ perms: ['task:view', 'data:view'] }), ['task:view', 'data:view'])
const allowed = new Set(['task:view', 'data:view'])
assert.equal(hasRoutePermissions({ perms: ['task:view', 'data:view'] }, (item) => allowed.has(item)), true)
allowed.delete('data:view')
assert.equal(hasRoutePermissions({ perms: ['task:view', 'data:view'] }, (item) => allowed.has(item)), false)
console.log('ROUTE_PERMISSIONS=PASS perms_and=true context_reauthorization=true')

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
  "http.getBlob('/api/excel/template', { expectedFile: 'xlsx' })",
  "{ expectedFile: 'zip' }",
  "store.hasPerm('excel:import')",
  "store.hasPerm('excel:match')",
  "store.hasPerm('excel:export')",
]) assert.ok(excelSource.includes(marker), marker)
const userSource = readFileSync(join(sourceRoot, 'stores/user.js'), 'utf8')
assert.match(userSource, /perms: \(s\) => s\.contextPermissions/)
assert.match(userSource, /async fetchMe\(\)[\s\S]+this\.selectTenant/)
assert.doesNotMatch(userSource, /profile\?\.role_code === 'super_admin'/)
const layoutSource = readFileSync(join(sourceRoot, 'layout/AdminLayout.vue'), 'utf8')
assert.match(layoutSource, /hasRoutePermissions\(route\.meta/)
assert.doesNotMatch(layoutSource, /router\.go\s*\(/)
console.log('SOURCE_CONTRACT=PASS http_imported=true direct_bypass=false selected_context_permissions=true')
