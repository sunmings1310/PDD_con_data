import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { pathToFileURL } from 'node:url'
import { compileScript, compileTemplate, parse } from '@vue/compiler-sfc'
import { createRenderer, h, nextTick, reactive, ref } from 'vue'

const webRoot = path.resolve(import.meta.dirname, '..')
const vueUrl = pathToFileURL(path.join(webRoot, 'node_modules/vue/index.mjs')).href
const utilsUrl = pathToFileURL(path.join(webRoot, 'src/utils/taskDraft.js')).href
const taskStatusUrl = pathToFileURL(path.join(webRoot, 'src/utils/taskStatus.js')).href

function deferred() {
  let resolve, reject
  const promise = new Promise((ok, fail) => { resolve = ok; reject = fail })
  return { promise, resolve, reject }
}

async function loadComponent(relative, injected = {}) {
  const filename = path.join(webRoot, relative)
  const descriptor = parse(fs.readFileSync(filename, 'utf8'), { filename }).descriptor
  const compiled = compileScript(descriptor, { id: relative })
  let script = compiled.content
  script = script
    .replace("from 'vue'", `from '${vueUrl}'`)
    .replace(/import \{ onBeforeRouteLeave, useRouter \} from 'vue-router'/, 'const useRouter = () => globalThis.__componentRouter; const onBeforeRouteLeave = (guard) => globalThis.__routeGuards.push(guard)')
    .replace(/import \{ useRouter \} from 'vue-router'/, 'const useRouter = () => globalThis.__componentRouter')
    .replace(/import \{ useRoute \} from 'vue-router'/, 'const useRoute = () => globalThis.__componentRoute')
    .replace(/import \{ useRoute, useRouter \} from 'vue-router'/, 'const useRoute = () => globalThis.__componentRoute; const useRouter = () => globalThis.__componentRouter')
    .replace(/import \{ ElMessage \} from 'element-plus'/, 'const ElMessage = globalThis.__componentMessage')
    .replace(/import \{ ElMessage, ElMessageBox \} from 'element-plus'/, 'const ElMessage = globalThis.__componentMessage; const ElMessageBox = globalThis.__componentMessageBox')
    .replace(/import \{ ElEmpty, ElTable, ElTableColumn \} from 'element-plus'/, 'const ElEmpty = globalThis.__componentStub; const ElTable = globalThis.__componentStub; const ElTableColumn = globalThis.__componentStub')
    .replace(/import http from '@\/api\/http'/, 'const http = globalThis.__componentHttp')
    .replace(/import ExcelMatch from '@\/views\/excel\/ExcelMatch\.vue'/, 'const ExcelMatch = globalThis.__ExcelMatch')
    .replace(/import \{ useUserStore \} from '@\/stores\/user'/, 'const useUserStore = () => globalThis.__componentStore')
    .replace("from '@/utils/taskDraft'", `from '${utilsUrl}'`)
    .replace("from '@/utils/taskStatus'", `from '${taskStatusUrl}'`)
    .replace("from '@/utils/requestGeneration'", `from '${pathToFileURL(path.join(webRoot, 'src/utils/requestGeneration.js')).href}'`)
    .replace(/import dayjs from 'dayjs'/, 'const dayjs = (value) => ({ toISOString: () => new Date(value).toISOString(), format: () => String(value) })')
  const template = compileTemplate({ source: descriptor.template.content, filename, id: relative, compilerOptions: { bindingMetadata: compiled.bindings } }).code
    .replace('from "vue"', `from '${vueUrl}'`)
    .replace('export function render', 'function render')
  script = script.replace('export default {', 'const __component = {')
  const source = `${script}\n${template}\n__component.render = render; export default __component;`
  return import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}#${Date.now()}${Math.random()}`)
}

const renderer = createRenderer({
  patchProp(el, key, _old, value) { el.props[key] = value },
  insert(el, parent) { parent.children.push(el); el.parent = parent },
  remove(el) { const index = el.parent?.children.indexOf(el); if (index >= 0) el.parent.children.splice(index, 1) },
  createElement(type) { return { type, props: {}, children: [] } },
  createText(text) { return { type: '#text', text } },
  createComment(text) { return { type: '#comment', text } },
  setText(node, text) { node.text = text },
  setElementText(node, text) { node.children = [{ type: '#text', text }] },
  parentNode(node) { return node.parent },
  nextSibling() { return null },
})
const stub = { render: () => null }
function mount(component, props = {}) {
  const app = renderer.createApp(component, props)
  for (const name of ['el-form', 'el-date-picker', 'el-pagination', 'el-drawer', 'el-descriptions', 'el-descriptions-item', 'el-row', 'el-col', 'el-card', 'el-statistic', 'el-space', 'el-tabs', 'el-tab-pane', 'el-text', 'el-form-item', 'el-input', 'el-radio-group', 'el-radio', 'el-radio-button', 'el-select', 'el-option', 'el-input-number', 'el-divider', 'el-checkbox', 'el-alert', 'el-table', 'el-table-column', 'el-button', 'el-upload', 'el-link', 'el-tag', 'el-dialog', 'el-image', 'el-empty']) app.component(name, stub)
  app.directive('loading', {})
  const root = { type: 'root', children: [] }
  return { proxy: app.mount(root), app }
}

globalThis.__componentMessage = { success() {}, warning() {}, error() {} }
globalThis.__componentMessageBox = { confirm: async () => true }
globalThis.__componentStub = { render: () => null }
globalThis.__componentStore = { hasPerm: () => true }
globalThis.__routeGuards = []
const matchRequests = []
globalThis.__componentHttp = {
  get: async () => ({ data: [] }),
  post(url, body, config) {
    const request = { url, body, config, deferred: deferred() }
    matchRequests.push(request)
    return request.deferred.promise
  },
  getBlob: async () => new Blob(), postBlob: async () => new Blob(),
}

const { default: ExcelMatch } = await loadComponent('src/views/excel/ExcelMatch.vue')
globalThis.__ExcelMatch = ExcelMatch

// Mount the actual embedded component and prove an old delayed A response is
// neither retained nor emitted after its parent platform switches to B.
const platform = reactive({ value: 'pinduoduo' })
const emitted = []
const child = ref(null)
const excelRoot = { render: () => h(ExcelMatch, { ref: child, embedded: true, platformCode: platform.value, onDraftRows: (rows) => emitted.push(rows) }) }
const excelApp = renderer.createApp(excelRoot)
for (const name of ['el-select', 'el-option', 'el-upload', 'el-button', 'el-table', 'el-table-column', 'el-link', 'el-tag', 'el-dialog', 'el-image', 'el-empty', 'el-alert']) excelApp.component(name, stub)
excelApp.directive('loading', {})
excelApp.mount({ type: 'root', children: [] })
await nextTick()
const upload = child.value.$.setupState.uploadMatch({ file: { name: 'a.xlsx' } })
assert.equal(matchRequests.length, 1)
platform.value = 'tmall'
await nextTick()
assert.equal(matchRequests[0].config.signal.aborted, true)
assert.equal(child.value.$.setupState.uploading, false)
matchRequests[0].deferred.resolve({ data: { rows: [{ row_index: 2, input_product_name: 'A' }] } })
await upload
await nextTick()
assert.equal(emitted.some((rows) => rows.some((row) => row.input_product_name === 'A')), false)
const secondUpload = child.value.$.setupState.uploadMatch({ file: { name: 'b.xlsx' } })
assert.equal(matchRequests.length, 2)
assert.equal(child.value.$.setupState.uploading, true)
matchRequests[1].deferred.resolve({ data: { rows: [{ row_index: 3, input_product_name: 'B' }] } })
await secondUpload
await nextTick()
assert.equal(child.value.$.setupState.uploading, false)
assert.equal(emitted.at(-1)[0].input_product_name, 'B')
const thirdUpload = child.value.$.setupState.uploadMatch({ file: { name: 'c.xlsx' } })
const beforeUnmountEmitCount = emitted.length
const excelState = child.value.$.setupState
excelApp.unmount()
assert.equal(matchRequests[2].config.signal.aborted, true)
assert.equal(excelState.uploading, false)
matchRequests[2].deferred.resolve({ data: { rows: [{ row_index: 4, input_product_name: 'C' }] } })
await thirdUpload
assert.equal(emitted.length, beforeUnmountEmitCount)
console.log('EXCEL_COMPONENT_RACE=PASS mounted=embedded signal_abort=platform+unmount uploading_reset=true retry_after_switch=true stale_rows_emit_fenced=true')

const posts = []
const pushes = []
globalThis.__componentRouter = { push: async (target) => { pushes.push(target) } }
globalThis.__componentHttp = {
  get: async () => ({ data: [] }),
  post(url, body) { const request = { url, body, deferred: deferred() }; posts.push(request); return request.deferred.promise },
}
const { default: TaskCreate } = await loadComponent('src/views/tasks/TaskCreate.vue')
const mounted = mount(TaskCreate)
await nextTick()
const taskState = mounted.proxy.$.setupState
taskState.form.keywordsText = 'first target'
await nextTick()
const first = taskState.submit()
const duplicate = taskState.submit()
assert.equal(posts.length, 2)
assert.deepEqual(posts[0].body, posts[1].body)
posts[0].deferred.reject(new Error('ACK_LOST'))
posts[1].deferred.resolve({ data: { task_id: 7, idempotent: true } })
await Promise.allSettled([first, duplicate])
const retry = taskState.submit()
assert.equal(posts[2].body.submission_id, posts[0].body.submission_id)
assert.deepEqual(posts[2].body, posts[0].body)
posts[2].deferred.resolve({ data: { task_id: 7, idempotent: true } })
await retry
taskState.form.keywordsText = 'edited target'
await nextTick()
const edited = taskState.submit()
assert.notEqual(posts[3].body.submission_id, posts[0].body.submission_id)
globalThis.__routeGuards.forEach((guard) => guard())
posts[3].deferred.resolve({ data: { task_id: 8 } })
await edited
assert.equal(pushes.includes('/tasks/8'), false)
console.log('TASK_CREATE_COMPONENT=PASS mounted=TaskCreate duplicate_click=same_payload ack_loss=replay edit=new_id route_stale=no_push')


// Mount the actual list, product, quality, and quarantine components with a
// controllable adapter.  The assertions exercise first load, refresh, error,
// retry, and context/route stale-response fences rather than source strings.
globalThis.__componentRoute = reactive({ params: {}, query: {}, fullPath: '/management/quarantines' })
globalThis.__componentStore = reactive({ enterpriseId: 'tenant-a', workspaceId: 'workspace-a', profile: {}, hasPerm: () => true })
const stateRequests = []
globalThis.__componentHttp = {
  get(url, options) { const request = { url, options, deferred: deferred() }; stateRequests.push(request); return request.deferred.promise },
  post: async () => ({ data: {} }), put: async () => ({ ok: true }), delete: async () => ({ ok: true }),
}

async function settle(request, data) { request.deferred.resolve({ data }); await request.deferred.promise; await nextTick() }
const { default: TaskList } = await loadComponent('src/views/tasks/TaskList.vue')
const taskList = mount(TaskList); await nextTick()
assert.equal(taskList.proxy.$.setupState.loading, true)
await settle(stateRequests.shift(), { items: [{ task_id: 1, status: 'pending' }], total: 1 })
assert.equal(taskList.proxy.$.setupState.loaded, true)
const taskRefreshA = taskList.proxy.$.setupState.load(); const taskRefreshB = taskList.proxy.$.setupState.load()
assert.equal(taskList.proxy.$.setupState.refreshing, true)
const staleTask = stateRequests.shift(); const currentTask = stateRequests.shift()
await settle(staleTask, { items: [{ task_id: 99, status: 'succeeded' }], total: 1 })
await settle(currentTask, { items: [{ task_id: 2, status: 'mystery' }], total: 1 }); await Promise.all([taskRefreshA, taskRefreshB])
assert.equal(taskList.proxy.$.setupState.list[0].task_id, 2)
assert.equal(taskList.proxy.$.setupState.statusText({ status: 'mystery' }), '未知状态（mystery）')
console.log('TASK_LIST_COMPONENT=PASS mounted=TaskList initial_loading background_refresh duplicate_refresh stale_response status_unknown_safe')
taskList.app.unmount()

const { default: ProductList } = await loadComponent('src/views/data/ProductList.vue')
const product = mount(ProductList); await nextTick()
const platformRequest = stateRequests.shift()
await settle(platformRequest, [])
const productInitial = stateRequests.shift(); await settle(productInitial, { items: [{ product_id: 1 }], total: 1 })
const productRefresh = product.proxy.$.setupState.load(); const oldProduct = stateRequests.shift()
globalThis.__componentStore.enterpriseId = 'tenant-b'; await nextTick()
const newProduct = stateRequests.shift(); await settle(oldProduct, { items: [{ product_id: 9 }], total: 1 }); await settle(newProduct, { items: [], total: 0 }); await productRefresh
assert.equal(product.proxy.$.setupState.list.length, 0); assert.equal(product.proxy.$.setupState.loaded, true); assert.equal(product.proxy.$.setupState.error, '')
console.log('PRODUCT_COMPONENT=PASS mounted=ProductList refresh_empty tenant_context_stale_fenced')
product.app.unmount()

const { default: QualityDashboard } = await loadComponent('src/views/management/QualityDashboard.vue')
const quality = mount(QualityDashboard); await nextTick()
const initialQuality = stateRequests.shift(); initialQuality.deferred.reject(new Error('quality down')); try { await initialQuality.deferred.promise } catch {} await nextTick()
assert.equal(quality.proxy.$.setupState.error, 'quality down')
const qualityRetry = quality.proxy.$.setupState.load(); const retryQuality = stateRequests.shift(); await settle(retryQuality, { overall: { total_count: 0 } }); await qualityRetry
assert.equal(quality.proxy.$.setupState.loaded, true); assert.equal(quality.proxy.$.setupState.error, '')
console.log('QUALITY_COMPONENT=PASS mounted=QualityDashboard initial_error retry empty_distinct')
quality.app.unmount()

const { default: QuarantineList } = await loadComponent('src/views/management/QuarantineList.vue')
const quarantine = mount(QuarantineList); await nextTick()
const initialQuarantine = stateRequests.shift(); await settle(initialQuarantine, { items: [{ quarantine_id: 1 }], total: 1 })
const oldQuarantine = quarantine.proxy.$.setupState.load(); const oldRequest = stateRequests.shift()
globalThis.__componentRoute.fullPath = '/management/quarantines?platform=jd'; await nextTick()
const freshRequest = stateRequests.shift(); await settle(oldRequest, { items: [{ quarantine_id: 88 }], total: 1 }); await settle(freshRequest, { items: [], total: 0 }); await oldQuarantine
assert.equal(quarantine.proxy.$.setupState.items.length, 0); assert.equal(quarantine.proxy.$.setupState.loaded, true)
console.log('QUARANTINE_COMPONENT=PASS mounted=QuarantineList refresh_empty route_context_stale_fenced')
