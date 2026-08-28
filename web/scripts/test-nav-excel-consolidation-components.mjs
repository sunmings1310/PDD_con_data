import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { pathToFileURL } from 'node:url'
import { compileScript, compileTemplate, parse } from '@vue/compiler-sfc'
import { createRenderer, h, nextTick, reactive } from 'vue'

const webRoot = path.resolve(import.meta.dirname, '..')
const vueUrl = pathToFileURL(path.join(webRoot, 'node_modules/vue/index.mjs')).href
const utilsUrl = pathToFileURL(path.join(webRoot, 'src/utils/taskDraft.js')).href
const requestGenerationUrl = pathToFileURL(path.join(webRoot, 'src/utils/requestGeneration.js')).href
const taskStatusUrl = pathToFileURL(path.join(webRoot, 'src/utils/taskStatus.js')).href

function deferred() {
  let resolve
  const promise = new Promise((ok) => { resolve = ok })
  return { promise, resolve }
}

async function loadComponent(relative) {
  const filename = path.join(webRoot, relative)
  const descriptor = parse(fs.readFileSync(filename, 'utf8'), { filename }).descriptor
  const compiled = compileScript(descriptor, { id: relative })
  let script = compiled.content
    .replace("from 'vue'", `from '${vueUrl}'`)
    .replace(/import \{ onBeforeRouteLeave, useRouter \} from 'vue-router'/, 'const useRouter = () => globalThis.__router; const onBeforeRouteLeave = () => {}')
    .replace(/import \{ useRoute \} from 'vue-router'/, 'const useRoute = () => globalThis.__route')
    .replace(/import \{ ElMessage \} from 'element-plus'/, 'const ElMessage = globalThis.__message')
    .replace(/import \{ ElMessage, ElMessageBox \} from 'element-plus'/, 'const ElMessage = globalThis.__message; const ElMessageBox = globalThis.__messageBox')
    .replace(/import http from '@\/api\/http'/, 'const http = globalThis.__http')
    .replace(/import ExcelMatch from '@\/views\/excel\/ExcelMatch\.vue'/, 'const ExcelMatch = globalThis.__ExcelMatch')
    .replace(/import \{ useUserStore \} from '@\/stores\/user'/, 'const useUserStore = () => globalThis.__store')
    .replace("from '@/utils/taskDraft'", `from '${utilsUrl}'`)
    .replace("from '@/utils/requestGeneration'", `from '${requestGenerationUrl}'`)
    .replace("from '@/utils/taskStatus'", `from '${taskStatusUrl}'`)
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
const button = { render() { return h('button', this.$attrs, this.$slots.default?.()) } }
function mount(component, props = {}) {
  const app = renderer.createApp(component, props)
  for (const name of ['el-radio-button', 'el-form', 'el-form-item', 'el-input', 'el-radio-group', 'el-radio', 'el-select', 'el-option', 'el-input-number', 'el-checkbox', 'el-divider', 'el-alert', 'el-table', 'el-table-column', 'el-upload', 'el-link', 'el-tag', 'el-dialog', 'el-image', 'el-empty', 'el-pagination', 'el-descriptions', 'el-descriptions-item']) app.component(name, stub)
  app.component('el-button', button)
  app.directive('loading', {})
  const root = { type: 'root', children: [] }
  return { proxy: app.mount(root), app, root }
}
function containsText(node, expected) {
  if (node.text?.includes(expected)) return true
  return (node.children || []).some((child) => containsText(child, expected))
}

globalThis.__message = { success() {}, warning() {}, error() {}, info() {} }
globalThis.__messageBox = { confirm: async () => true }
const pushed = []
globalThis.__router = { push: async (target) => { pushed.push(target) } }
globalThis.__route = reactive({ query: { source: 'excel' }, params: {}, fullPath: '/tasks/create?source=excel' })
globalThis.__store = reactive({ enterpriseId: 'tenant-a', workspaceId: 'workspace-a', hasPerm: () => true })
globalThis.__http = { get: async () => ({ data: [] }), post: async () => ({ data: { task_id: 1 } }), getBlob: async () => new Blob(), postBlob: async () => new Blob() }

const { default: ExcelMatch } = await loadComponent('src/views/excel/ExcelMatch.vue')
globalThis.__ExcelMatch = ExcelMatch
const { default: TaskCreate } = await loadComponent('src/views/tasks/TaskCreate.vue')
const task = mount(TaskCreate)
await nextTick()
assert.equal(task.proxy.$.setupState.source, 'excel')
globalThis.__route.query.source = 'unexpected'
await nextTick()
assert.equal(task.proxy.$.setupState.source, 'manual')
task.proxy.$.setupState.form.keywordsText = 'route stale target'
await nextTick()
const staleSubmit = deferred()
globalThis.__http.post = (_url, _body, config) => { staleSubmit.config = config; return staleSubmit.promise }
const submitting = task.proxy.$.setupState.submit()
globalThis.__route.fullPath = '/tasks/create?source=excel'
globalThis.__route.query.source = 'excel'
await nextTick()
assert.equal(staleSubmit.config.signal.aborted, true)
assert.equal(task.proxy.$.setupState.loading, false)
staleSubmit.resolve({ data: { task_id: 99 } })
await submitting
assert.equal(pushed.includes('/tasks/99'), false)
task.app.unmount()
console.log('TASK_CREATE_QUERY=PASS mounted=TaskCreate source_excel=selected invalid_source=manual route_stale=abort_no_navigation loading_reset=true')

const taskEmits = []
const taskMode = mount(ExcelMatch, { embedded: true, mode: 'task-import', platformCode: 'pinduoduo', onDraftRows: (rows) => taskEmits.push(rows) })
await nextTick()
const taskRequest = deferred()
globalThis.__http.post = () => taskRequest.promise
const taskUpload = taskMode.proxy.$.setupState.uploadMatch({ file: { name: 'task.xlsx' } })
taskRequest.resolve({ data: { rows: [{ row_index: 1, input_product_name: '任务行' }], total: 1 } })
await taskUpload
await nextTick()
assert.equal(taskMode.proxy.$.setupState.isTaskImport, true)
assert.equal(taskEmits.length, 1)
assert.equal(containsText(taskMode.root, '批量导出'), false)
taskMode.app.unmount()

const libraryEmits = []
const libraryMode = mount(ExcelMatch, { mode: 'library-match', onDraftRows: (rows) => libraryEmits.push(rows) })
await nextTick()
const libraryRequest = deferred()
globalThis.__http.post = () => libraryRequest.promise
const libraryUpload = libraryMode.proxy.$.setupState.uploadMatch({ file: { name: 'library.xlsx' } })
libraryRequest.resolve({ data: { rows: [{ row_index: 2, input_product_name: '资料库行' }], total: 1 } })
await libraryUpload
await nextTick()
assert.equal(libraryMode.proxy.$.setupState.isLibraryMatch, true)
assert.equal(libraryEmits.length, 0)
assert.equal(containsText(libraryMode.root, '批量导出'), true)
libraryMode.app.unmount()
console.log('EXCEL_MODE_COMPONENT=PASS mounted=ExcelMatch task_import=emit_no_export library_match=no_emit_export_visible direct_dispatch_absent=true')

const { default: ProductList } = await loadComponent('src/views/data/ProductList.vue')
globalThis.__store = reactive({ enterpriseId: 'tenant-a', workspaceId: 'workspace-a', hasPerm: (permission) => permission !== 'excel:match' })
globalThis.__http = { get: async () => ({ data: [] }), post: async () => ({ data: {} }), getBlob: async () => new Blob() }
const noExcelPermission = mount(ProductList)
await nextTick()
assert.equal(containsText(noExcelPermission.root, 'Excel 批量查库/导出'), false)
noExcelPermission.app.unmount()
globalThis.__store = reactive({ enterpriseId: 'tenant-a', workspaceId: 'workspace-a', hasPerm: () => true })
const excelPermission = mount(ProductList)
await nextTick()
assert.equal(containsText(excelPermission.root, 'Excel 批量查库/导出'), true)
excelPermission.app.unmount()
console.log('PRODUCT_ENTRY_COMPONENT=PASS mounted=ProductList excel_match_permission=required entry_target=/products/excel-match')

const routerUrl = pathToFileURL(path.join(webRoot, 'node_modules/vue-router/dist/vue-router.esm-bundler.js')).href
let routerSource = fs.readFileSync(path.join(webRoot, 'src/router/index.js'), 'utf8')
routerSource = routerSource
  .replace("import { createRouter, createWebHistory } from 'vue-router'", `import { createRouter, createMemoryHistory } from '${routerUrl}'`)
  .replace("import { useUserStore } from '@/stores/user'", 'const useUserStore = () => globalThis.__routerStore')
  .replace(/import \{ hasRoutePermissions \} from ['"](?:@\/router\/permissions|\.\/permissions\.js)['"]/ , 'const hasRoutePermissions = (meta, has) => (meta.perms || (meta.perm ? [meta.perm] : [])).every(has)')
  .replace('createWebHistory()', 'createMemoryHistory()')
  .replaceAll("import('@/", "Promise.resolve('")
globalThis.__routerStore = { token: 'test', profile: {}, hasPerm: () => true, fetchMe: async () => {}, logout() {} }
const { default: actualRouter } = await import(`data:text/javascript;base64,${Buffer.from(routerSource).toString('base64')}#${Date.now()}`)
await actualRouter.push('/excel')
assert.equal(actualRouter.currentRoute.value.fullPath, '/tasks/create?source=excel')
const libraryRoute = actualRouter.resolve('/products/excel-match')
assert.deepEqual(libraryRoute.meta.perms, ['data:view', 'excel:match'])
assert.equal(fs.readFileSync(path.join(webRoot, 'src/layout/AdminLayout.vue'), 'utf8').includes('index="/excel"'), false)
assert.equal(fs.readFileSync(path.join(webRoot, 'src/views/excel/ExcelMatch.vue'), 'utf8').includes('/api/excel/unmatched-to-task'), false)
console.log('NAV_ROUTER_CONTRACT=PASS actual_router excel_redirect=/tasks/create?source=excel product_library_permission=data:view+excel:match top_level_excel_menu=absent')
