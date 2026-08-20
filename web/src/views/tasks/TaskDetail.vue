<template>
  <div>
    <div class="page-card">
      <div class="toolbar">
        <el-button @click="$router.back()">返回</el-button>
        <el-button type="primary" @click="load">刷新</el-button>
        <el-button type="success" @click="$router.push(`/tasks/${route.params.id}/trace`)">查看执行轨迹</el-button>
        <el-button v-if="task?.device_id && store.hasPerm('device:cast')" @click="$router.push(`/devices/${task.device_id}/cast`)">关联设备投屏</el-button>
      </div>
      <el-descriptions v-if="task" :column="3" border>
        <el-descriptions-item label="任务">#{{ task.task_id }} {{ task.task_name }}</el-descriptions-item>
        <el-descriptions-item label="平台">{{ task.platform_code }}</el-descriptions-item>
        <el-descriptions-item label="任务状态">
          <el-tag :type="taskStatusType(task.status)">{{ task.ui_status }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="进度">
          成功 {{ okItems.length }} / 失败 {{ failItems.length }} / 待处理 {{ pendingItems.length }} / 目标 {{ items.length }}
        </el-descriptions-item>
        <el-descriptions-item label="设备">{{ task.device_id || '-' }}</el-descriptions-item>
        <el-descriptions-item label="创建人">{{ task.create_username || '-' }}</el-descriptions-item>
        <el-descriptions-item v-if="isMatchTask" label="匹配结果">
          匹配成功 {{ matchOkItems.length }} / 匹配失败 {{ matchFailItems.length }} / 待匹配 {{ matchPendingItems.length }}
        </el-descriptions-item>
        <el-descriptions-item v-if="task.error_msg" label="任务错误" :span="3">
          <el-text type="danger">{{ task.error_msg }}</el-text>
        </el-descriptions-item>
      </el-descriptions>
      <el-progress v-if="task" style="margin-top:12px" :percentage="percent" />
    </div>

    <div class="page-card">
      <h3 class="section-title">实时采集日志</h3>
      <el-table :data="task?.logs || []" height="280" border>
        <el-table-column label="时间" width="180">
          <template #default="{ row }">{{ fmt(row.create_time) }}</template>
        </el-table-column>
        <el-table-column prop="level_code" label="级别" width="90" />
        <el-table-column prop="message" label="内容" />
      </el-table>
    </div>

    <div class="page-card" v-if="taskProducts.length">
      <div class="toolbar"><h3 class="section-title" style="margin:0;flex:1">本次采集商品（{{ taskProducts.length }}）</h3><el-button v-if="task?.can_manage_results" type="success" :disabled="!selectedProducts.length" @click="saveToLibrary">保存选中到商品资料库</el-button></div>
      <el-table :data="taskProducts" border stripe @selection-change="selectedProducts=$event">
        <el-table-column type="selection" width="48" :selectable="row=>row.library_status!=='saved'" />
        <el-table-column prop="product_id" label="ID" width="80" /><el-table-column prop="canonical_name" label="规范商品名称" min-width="170" /><el-table-column prop="platform_title" label="平台完整标题" min-width="190" show-overflow-tooltip /><el-table-column prop="product_attribute_spec" label="商品属性规格" width="150" /><el-table-column prop="approval_number" label="批准文号" width="180" /><el-table-column prop="manufacturer" label="生产厂家" min-width="170" />
        <el-table-column label="状态" width="100"><template #default="{row}"><el-tag :type="row.library_status==='saved'?'success':'warning'">{{ row.library_status==='saved'?'已入库':'待保存' }}</el-tag></template></el-table-column>
        <el-table-column v-if="task?.can_manage_results" label="操作" width="140"><template #default="{row}"><el-button link type="primary" @click="editProduct(row)">修改</el-button><el-button link type="danger" @click="deleteProduct(row)">删除</el-button></template></el-table-column>
      </el-table>
      <el-pagination v-model:current-page="productPage" v-model:page-size="productLimit"
        :total="productTotal" :page-sizes="[20,50,100]" layout="total, sizes, prev, pager, next"
        style="margin-top:16px;justify-content:flex-end" @change="loadProducts" />
    </div>

    <div class="page-card" v-if="task?.anomalies?.length">
      <h3 class="section-title">异常记录（{{ task.anomalies.length }}）</h3>
      <el-table :data="task.anomalies" border stripe>
        <el-table-column label="时间" width="170"><template #default="{row}">{{ fmt(row.create_time) }}</template></el-table-column><el-table-column prop="action_name" label="动作" width="140" /><el-table-column prop="consecutive_count" label="连续次数" width="90" /><el-table-column prop="message" label="异常说明" min-width="220" /><el-table-column prop="page_text" label="页面摘要" min-width="220" show-overflow-tooltip /><el-table-column label="截图" width="100"><template #default="{row}"><el-image v-if="row.screenshot_url" :src="row.screenshot_url" :preview-src-list="[row.screenshot_url]" style="width:64px;height:64px" fit="cover" preview-teleported /></template></el-table-column>
      </el-table>
    </div>

    <div class="page-card">
      <div class="toolbar">
        <h3 class="section-title" style="margin:0;flex:1">明细列表</h3>
        <el-button type="danger" plain :disabled="!retryItems.length" @click="requeueFails">失败/未完成条目重新下发</el-button>
      </div>
        <el-tabs>
          <el-tab-pane :label="`全部(${items.length})`">
            <el-table :data="items" border stripe>
              <el-table-column prop="row_index" label="#" width="70" />
              <el-table-column prop="keyword" label="搜索目标" min-width="160" show-overflow-tooltip />
              <el-table-column prop="target_approval" label="目标准字" min-width="170" show-overflow-tooltip />
              <el-table-column prop="target_spec" label="目标规格" min-width="150" show-overflow-tooltip />
              <el-table-column label="采集状态" width="110">
                <template #default="{ row }"><el-tag :type="itemStatusType(row.status)" size="small">{{ itemStatusText(row.status) }}</el-tag></template>
              </el-table-column>
              <el-table-column label="匹配结果" width="120">
                <template #default="{ row }"><el-tag :type="matchStatusType(row)" size="small">{{ matchStatusText(row) }}</el-tag></template>
              </el-table-column>
              <el-table-column prop="product_id" label="商品ID" width="110">
                <template #default="{ row }">{{ row.product_id || '-' }}</template>
              </el-table-column>
              <el-table-column prop="message" label="结果说明" min-width="230" show-overflow-tooltip />
              <el-table-column label="更新时间" width="165"><template #default="{ row }">{{ fmt(row.update_time) }}</template></el-table-column>
            </el-table>
          </el-tab-pane>
          <el-tab-pane :label="`成功(${okItems.length})`">
            <el-table :data="okItems" border stripe>
              <el-table-column prop="row_index" label="#" width="70" />
              <el-table-column prop="keyword" label="搜索目标" />
              <el-table-column prop="target_approval" label="目标准字" min-width="170" />
              <el-table-column prop="target_spec" label="目标规格" min-width="150" />
              <el-table-column prop="product_id" label="商品ID" width="120" />
              <el-table-column prop="message" label="结果说明" min-width="220" />
            </el-table>
          </el-tab-pane>
          <el-tab-pane :label="`失败(${failItems.length})`">
            <el-table :data="failItems" border stripe>
              <el-table-column prop="row_index" label="#" width="70" />
              <el-table-column prop="keyword" label="搜索目标" />
              <el-table-column prop="target_approval" label="目标准字" min-width="170" />
              <el-table-column prop="target_spec" label="目标规格" min-width="150" />
              <el-table-column prop="message" label="失败/未匹配原因" min-width="260" />
            </el-table>
          </el-tab-pane>
          <el-tab-pane :label="`待处理(${pendingItems.length})`">
            <el-table :data="pendingItems" border stripe>
              <el-table-column prop="row_index" label="#" width="70" />
              <el-table-column prop="keyword" label="搜索目标" />
              <el-table-column prop="target_approval" label="目标准字" min-width="170" />
              <el-table-column prop="target_spec" label="目标规格" min-width="150" />
              <el-table-column label="状态" width="120"><template #default="{ row }">{{ itemStatusText(row.status) }}</template></el-table-column>
            </el-table>
          </el-tab-pane>
      </el-tabs>
    </div>
    <el-dialog v-model="editVisible" title="修改本次采集稳定资料" width="650px"><el-form label-width="120px"><el-form-item label="平台完整标题"><el-input v-model="editForm.platform_title" /></el-form-item><el-form-item label="规范商品名称"><el-input v-model="editForm.canonical_name" /></el-form-item><el-form-item label="品牌"><el-input v-model="editForm.brand" /></el-form-item><el-form-item label="商品属性规格"><el-input v-model="editForm.product_attribute_spec" /></el-form-item><el-form-item label="批准文号"><el-input v-model="editForm.approval_number" /></el-form-item><el-form-item label="生产厂家"><el-input v-model="editForm.manufacturer" /></el-form-item></el-form><template #footer><el-button @click="editVisible=false">取消</el-button><el-button type="primary" @click="saveProductEdit">保存</el-button></template></el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import dayjs from 'dayjs'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/api/http'
import { useUserStore } from '@/stores/user'

const route = useRoute()
const router = useRouter()
const store = useUserStore()
const task = ref(null)
const taskProducts = ref([])
const selectedProducts = ref([])
const productPage = ref(1)
const productLimit = ref(50)
const productTotal = ref(0)
const editVisible = ref(false)
const editForm = reactive({product_id:null,scope:'capture',platform_title:'',canonical_name:'',brand:'',product_attribute_spec:'',approval_number:'',manufacturer:'',dosage_form:'',category:'',expiry:''})
let timer

const items = computed(() => task.value?.items || [])
const okItems = computed(() => items.value.filter((x) => ['succeeded', 'done'].includes(x.status)))
const failItems = computed(() => items.value.filter((x) => ['failed', 'not_matched'].includes(x.status)))
const retryItems = computed(() => items.value.filter((x) => ['failed', 'not_matched', 'cancelled'].includes(x.status)))
const pendingItems = computed(() => items.value.filter((x) => !['succeeded', 'done', 'failed', 'not_matched', 'cancelled'].includes(x.status)))
const isMatchTask = computed(() => items.value.some((x) => x.target_approval && x.target_spec))
const matchOkItems = computed(() => okItems.value.filter((x) => x.target_approval && x.target_spec))
const matchFailItems = computed(() => failItems.value.filter((x) => x.target_approval && x.target_spec))
const matchPendingItems = computed(() => pendingItems.value.filter((x) => x.target_approval && x.target_spec))
const percent = computed(() => {
  if (!items.value.length) return 0
  return Math.min(100, Math.round(((okItems.value.length + failItems.value.length) / items.value.length) * 100))
})

function fmt(v) { return v ? dayjs(v).format('YYYY-MM-DD HH:mm:ss') : '-' }

function itemStatusText(status) {
  return { pending: '待采集', running: '采集中', succeeded: '采集成功', done: '采集成功', not_matched: '未匹配', failed: '采集失败', cancelled: '已取消' }[status] || status || '-'
}
function itemStatusType(status) {
  return { pending: 'info', running: 'warning', succeeded: 'success', done: 'success', not_matched: 'warning', failed: 'danger', cancelled: 'info' }[status] || 'info'
}
function matchStatusText(row) {
  if (!row.target_approval || !row.target_spec) return '-'
  if (['succeeded', 'done'].includes(row.status)) return '匹配成功'
  if (row.status === 'not_matched') return '未匹配'
  if (row.status === 'failed') return '匹配失败'
  if (row.status === 'cancelled') return '已取消'
  return '待匹配'
}
function matchStatusType(row) {
  return { succeeded: 'success', done: 'success', not_matched: 'warning', failed: 'danger', cancelled: 'info' }[row.status] || 'warning'
}
function taskStatusType(status) {
  return { pending: 'info', running: 'warning', succeeded: 'success', partially_succeeded: 'warning', done: 'success', failed: 'danger', cancelled: 'info', timed_out: 'danger' }[status] || 'info'
}

async function load() {
  const [res] = await Promise.all([http.get(`/api/tasks/${route.params.id}`), loadProducts()])
  task.value = res.data
}

async function loadProducts() {
  const products = await http.get(`/api/products?task_id=${route.params.id}&page=${productPage.value}&limit=${productLimit.value}`)
  taskProducts.value = products.data?.items || []
  productTotal.value = Number(products.data?.total || 0)
}

async function editProduct(row){
  const res=await http.get(`/api/products/${row.product_id}/edit?scope=capture`)
  Object.assign(editForm,res.data)
  editVisible.value=true
}
async function saveProductEdit(){
  const {product_id,...payload}=editForm
  const res=await http.put(`/api/products/${product_id}`,payload)
  if(res.ok){ElMessage.success('已保存');editVisible.value=false;load()}
}
async function deleteProduct(row){await ElMessageBox.confirm(`仅删除本次任务商品 #${row.product_id}，确认继续？`,'提示',{type:'warning'});const res=await http.delete(`/api/products/${row.product_id}`);if(res.ok){ElMessage.success('已删除');load()}}
async function saveToLibrary(){const res=await http.post('/api/products/save-batch',{product_ids:selectedProducts.value.map(x=>x.product_id)});if(res.ok){ElMessage.success(res.message);load()}}

async function requeueFails() {
  if (!retryItems.value.length) return
  await ElMessageBox.confirm(
    `将重新下发 ${retryItems.value.length} 条，并完整保留原批准文号、品名、规格、厂家及任务配置。`,
    '确认重新下发',
    { type: 'warning' },
  )
  const res = await http.post(`/api/tasks/${route.params.id}/requeue-failed`, { include_cancelled: true })
  if (!res.ok) return
  ElMessage.success(`已重新下发 #${res.data.task_id}，保留匹配目标 ${res.data.match_target_count} 条`)
  router.push(`/tasks/${res.data.task_id}`)
}

onMounted(() => {
  load()
  timer = setInterval(load, 5000)
})
onUnmounted(() => clearInterval(timer))
</script>
