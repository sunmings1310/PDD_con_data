<template>
  <div :class="embedded ? 'excel-match-page embedded-excel' : 'page-card excel-match-page'">
    <div class="page-head">
      <div>
        <h2 v-if="!embedded" class="page-title">Excel 导入匹配</h2>
        <div class="page-subtitle">按“国药准字 + 品名 + 规格 + 生产厂家”匹配，保留原始行</div>
      </div>
      <div class="toolbar">
        <el-select
          v-model="platform"
          placeholder="请选择平台"
          style="width: 180px"
          :disabled="uploading || dispatching"
        >
          <el-option
            v-for="item in platforms"
            :key="item.platform_code"
            :label="item.platform_name"
            :value="item.platform_code"
          />
        </el-select>
        <el-select
          v-model="deviceId"
          clearable
          filterable
          placeholder="请选择采集设备"
          no-data-text="当前平台没有在线设备"
          style="width: 240px"
          :disabled="dispatching"
        >
          <el-option
            v-for="device in availableDevices"
            :key="device.device_id"
            :label="`${device.device_name || device.device_key}（${device.ui_status}）`"
            :value="device.device_id"
          />
        </el-select>
        <el-select v-model="maxDetail" style="width: 150px" :disabled="dispatching" title="每条目标最多核对商品数">
          <el-option :value="5" label="每项核对 5 个" />
          <el-option :value="10" label="每项核对 10 个" />
          <el-option :value="20" label="每项核对 20 个" />
          <el-option :value="30" label="每项核对 30 个" />
        </el-select>
        <el-upload
          v-if="store.hasPerm('excel:match')"
          :show-file-list="false"
          :http-request="uploadMatch"
          :before-upload="beforeUpload"
          accept=".xlsx,.xls"
        >
          <el-button type="primary" :loading="uploading">导入 Excel</el-button>
        </el-upload>
        <el-button v-if="store.hasPerm('excel:import')" @click="downloadTemplate">下载模板</el-button>
        <el-button v-if="store.hasPerm('excel:export')" type="success" :disabled="!selectedRows.length" :loading="exporting" @click="exportBatch">
          批量导出（{{ selectedRows.length }}）
        </el-button>
        <el-button
          type="warning"
          :disabled="!unmatchedRows.length"
          :loading="dispatching"
          @click="dispatchAndroidMatch"
        >
          安卓采集未匹配（{{ unmatchedRows.length }}）
        </el-button>
      </div>
    </div>

    <el-alert
      v-if="stats"
      :title="`共 ${stats.total} 行：唯一匹配 ${stats.unique} 行，多匹配 ${stats.multiple} 行，未匹配 ${stats.unmatched} 行`"
      type="info"
      show-icon
      :closable="false"
      style="margin-bottom: 14px"
    />

    <el-table
      ref="tableRef"
      v-loading="uploading"
      :data="rows"
      row-key="row_index"
      border
      stripe
      height="620"
      @selection-change="selectedRows = $event"
    >
      <el-table-column type="selection" width="48" :selectable="(row) => row.matched" fixed />
      <el-table-column prop="input_product_name" label="原始品名" min-width="150" show-overflow-tooltip />
      <el-table-column prop="input_spec" label="原始规格" width="130" show-overflow-tooltip />
      <el-table-column prop="product_id" label="商品 id" width="100" fixed />
      <el-table-column prop="product_name" label="商品名称" min-width="180" show-overflow-tooltip />
      <el-table-column prop="sell_name" label="品名" min-width="160" show-overflow-tooltip />
      <el-table-column prop="spec" label="规格" width="150" show-overflow-tooltip />
      <el-table-column prop="approval_no" label="国药准字" width="180" show-overflow-tooltip />
      <el-table-column prop="brand" label="品牌" width="120" show-overflow-tooltip />
      <el-table-column prop="manufacturer" label="生产厂家" min-width="190" show-overflow-tooltip />
      <el-table-column label="goodsid 列表价" width="135">
        <template #default="{ row }">{{ formatPrice(row.list_price) }}</template>
      </el-table-column>
      <el-table-column prop="multi_spec_prices" label="goodsid 多规格售价" min-width="220" show-overflow-tooltip />
      <el-table-column prop="price_range" label="售价区间" width="145" />
      <el-table-column label="商品主图" width="96" align="center">
        <template #default="{ row }">
          <el-image
            v-if="row.main_image"
            :src="row.main_image"
            :preview-src-list="[row.main_image]"
            preview-teleported
            fit="cover"
            class="thumb"
          />
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="匹配状态" width="120" fixed="right">
        <template #default="{ row }">
          <el-tag :type="statusType(row.match_status)" size="small">{{ statusText(row.match_status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="130" fixed="right">
        <template #default="{ row }">
          <el-link v-if="row.match_status === 'multiple'" type="primary" @click="openCandidates(row)">
            查看全部匹配
          </el-link>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
      <template #empty>
        <el-empty description="请选择平台并导入 Excel；必填列为国药准字、品名、规格、生产厂家" />
      </template>
    </el-table>

    <el-dialog v-model="candidateDialog" title="全部匹配商品" width="1100px" destroy-on-close>
      <el-table :data="activeRow?.candidates || []" border stripe max-height="520">
        <el-table-column prop="product_id" label="商品 id" width="100" />
        <el-table-column prop="product_name" label="商品名称" min-width="180" show-overflow-tooltip />
        <el-table-column prop="sell_name" label="品名" min-width="150" show-overflow-tooltip />
        <el-table-column prop="spec" label="规格" width="140" />
        <el-table-column prop="approval_no" label="国药准字" width="170" />
        <el-table-column prop="manufacturer" label="生产厂家" min-width="180" show-overflow-tooltip />
        <el-table-column label="列表价" width="100">
          <template #default="{ row }">{{ formatPrice(row.list_price) }}</template>
        </el-table-column>
        <el-table-column prop="price_range" label="售价区间" width="140" />
        <el-table-column label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link @click="chooseCandidate(row)">选择</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import http from '@/api/http'
import { useUserStore } from '@/stores/user'

const platforms = ref([])
const { embedded = false } = defineProps({ embedded: Boolean })
const devices = ref([])
const router = useRouter()
const store = useUserStore()
const platform = ref('pinduoduo')
const deviceId = ref(null)
const maxDetail = ref(10)
const rows = ref([])
const stats = ref(null)
const selectedRows = ref([])
const uploading = ref(false)
const exporting = ref(false)
const dispatching = ref(false)
const candidateDialog = ref(false)
const activeRow = ref(null)
const tableRef = ref(null)
const unmatchedRows = computed(() => rows.value.filter((row) => !row.matched))
const availableDevices = computed(() => devices.value.filter(
  (device) => device.online && device.platform_code === platform.value,
))

watch(availableDevices, (items) => {
  if (!items.some((device) => device.device_id === deviceId.value)) {
    deviceId.value = items.length === 1 ? items[0].device_id : null
  }
})

function beforeUpload(file) {
  if (!platform.value) {
    ElMessage.warning('请先选择平台')
    return false
  }
  if (!/\.(xlsx|xls)$/i.test(file.name)) {
    ElMessage.error('仅支持 .xlsx/.xls 文件')
    return false
  }
  return true
}

async function downloadTemplate() {
  const blob = await http.getBlob('/api/excel/template', { expectedFile: 'xlsx' })
  downloadBlob(blob, '商品资料库匹配模板.xlsx')
}

async function uploadMatch({ file }) {
  uploading.value = true
  selectedRows.value = []
  try {
    const form = new FormData()
    form.append('file', file)
    const response = await http.post(
      `/api/excel/match?platform_code=${encodeURIComponent(platform.value)}`,
      form,
    )
    rows.value = response.data.rows || []
    stats.value = response.data
    ElMessage.success('匹配完成')
  } finally {
    uploading.value = false
  }
}

function openCandidates(row) {
  activeRow.value = row
  candidateDialog.value = true
}

function chooseCandidate(candidate) {
  if (!activeRow.value) return
  const keep = {
    row_index: activeRow.value.row_index,
    input_approval_no: activeRow.value.input_approval_no,
    input_spec: activeRow.value.input_spec,
    matched: true,
    match_status: 'multiple',
    match_count: activeRow.value.match_count,
    candidates: activeRow.value.candidates,
  }
  Object.assign(activeRow.value, candidate, keep)
  candidateDialog.value = false
  ElMessage.success('已替换为所选商品')
}

async function exportBatch() {
  exporting.value = true
  try {
    const blob = await http.postBlob(
      '/api/excel/export-batch',
      { platform_code: platform.value, rows: selectedRows.value },
      { expectedFile: 'zip' },
    )
    const platformName = platforms.value.find((item) => item.platform_code === platform.value)?.platform_name || platform.value
    const timestamp = new Date().toISOString().replace(/[-:T]/g, '').slice(0, 14)
    downloadBlob(blob, `${platformName}_${timestamp}.zip`)
    ElMessage.success('导出压缩包已生成')
  } finally {
    exporting.value = false
  }
}

async function dispatchAndroidMatch() {
  if (!deviceId.value) {
    ElMessage.warning('请先选择在线采集设备')
    return
  }
  dispatching.value = true
  try {
    const response = await http.post('/api/excel/unmatched-to-task', {
      platform_code: platform.value,
      device_id: deviceId.value,
      rows: unmatchedRows.value,
      max_detail: maxDetail.value,
      task_name: `Excel安卓匹配-${new Date().toLocaleString()}`,
    })
    ElMessage.success(`已下发 ${response.data.count} 行，任务 #${response.data.task_id}`)
    router.push(`/tasks/${response.data.task_id}`)
  } finally {
    dispatching.value = false
  }
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

function formatPrice(value) {
  if (value === null || value === undefined || value === '') return '—'
  const number = Number(value)
  return Number.isFinite(number) ? `¥${number}` : String(value)
}

function statusType(status) {
  return { unique: 'success', multiple: 'warning', unmatched: 'danger' }[status] || 'info'
}

function statusText(status) {
  return { unique: '唯一匹配', multiple: '多匹配项', unmatched: '未匹配' }[status] || '未知'
}

onMounted(async () => {
  const [platformResponse, deviceResponse] = await Promise.all([
    http.get('/api/platforms'),
    http.get('/api/devices'),
  ])
  platforms.value = platformResponse.data || []
  devices.value = deviceResponse.data || []
  if (!platforms.value.some((item) => item.platform_code === platform.value) && platforms.value.length) {
    platform.value = platforms.value[0].platform_code
  }
})
</script>

<style scoped>
.excel-match-page { min-width: 0; }
.page-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; margin-bottom: 16px; }
.page-title { margin-bottom: 4px; }
.page-subtitle { color: #909399; font-size: 13px; }
.toolbar { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 10px; }
.thumb { width: 52px; height: 52px; border-radius: 6px; }
.muted { color: #c0c4cc; }
</style>
