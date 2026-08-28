<template>
  <div class="page-card">
    <div class="toolbar">
      <el-select v-model="status" clearable placeholder="全部状态" style="width:140px" @change="applyFilters">
        <el-option label="待下发" value="pending" />
        <el-option label="执行中" value="running" />
        <el-option label="全部成功" value="succeeded" />
        <el-option label="部分成功" value="partially_succeeded" />
        <el-option label="执行失败" value="failed" />
        <el-option label="已取消" value="cancelled" />
        <el-option label="已超时" value="timed_out" />
      </el-select>
      <el-button @click="load">刷新</el-button>
      <el-button v-if="store.hasPerm('task:create')" type="primary" @click="$router.push('/tasks/create')">创建任务</el-button>
    </div>
    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" style="margin-bottom:12px">
      <template #default><el-button link type="primary" @click="load">重试</el-button></template>
    </el-alert>
    <div v-if="refreshing" class="refreshing-hint">正在刷新，保留当前任务列表</div>
      <el-table v-loading="loading" :data="list" stripe border @row-click="goDetail">
      <template #empty><el-empty v-if="loaded && !error" description="暂无任务" /></template>
      <el-table-column prop="task_id" label="任务ID" width="90" />
      <el-table-column prop="task_name" label="任务名称" min-width="160" />
      <el-table-column prop="platform_code" label="平台" width="110" />
      <el-table-column label="状态" width="110">
        <template #default="{ row }">
          <el-tag :type="tagType(row)" effect="light">{{ statusText(row) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="数量" width="160">
        <template #default="{ row }">{{ countText(row) }}</template>
      </el-table-column>
      <el-table-column prop="create_username" label="创建人" width="110" />
      <el-table-column label="审核" width="180">
        <template #default="{ row }">
          <el-tag :type="row.review_status === 'approved' ? 'success' : row.review_status === 'rejected' ? 'danger' : 'warning'">
            {{ reviewText(row.review_status) }}
          </el-tag>
          <template v-if="row.review_status === 'pending' && row.can_review && store.hasPerm('task:review')">
            <el-button link type="success" @click.stop="review(row, 'approved')">通过</el-button>
            <el-button link type="danger" @click.stop="review(row, 'rejected')">驳回</el-button>
          </template>
        </template>
      </el-table-column>
      <el-table-column prop="device_id" label="执行设备" width="100" />
      <el-table-column label="创建时间" width="170">
        <template #default="{ row }">{{ fmt(row.create_time) }}</template>
      </el-table-column>
    </el-table>
    <el-pagination
      v-model:current-page="page"
      v-model:page-size="limit"
      :total="total"
      :page-sizes="[20, 50, 100]"
      layout="total, sizes, prev, pager, next"
      style="margin-top:16px;justify-content:flex-end"
      @change="load"
    />
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import dayjs from 'dayjs'
import http from '@/api/http'
import { useUserStore } from '@/stores/user'
import { createRequestGeneration } from '@/utils/requestGeneration'
import { taskStatusText, taskStatusType, viewScope } from '@/utils/taskStatus'

const store = useUserStore()
const router = useRouter()
const list = ref([])
const status = ref('')
const loading = ref(false)
const refreshing = ref(false)
const loaded = ref(false)
const page = ref(1)
const limit = ref(20)
const total = ref(0)
const error = ref('')

function fmt(v) { return v ? dayjs(v).format('YYYY-MM-DD HH:mm:ss') : '-' }
function countText(row) {
  return `${row.success_count || 0}/${row.fail_count || 0} / ${row.target_count || 0}`
}
const requestGeneration = createRequestGeneration()
const scope = computed(() => viewScope(store.enterpriseId, store.workspaceId, status.value, page.value, limit.value))
function tagType(row) { return taskStatusType(row.status) }
function statusText(row) { return taskStatusText(row.status, row.ui_status) }
function goDetail(row) {
  router.push(`/tasks/${row.task_id}`)
}
function reviewText(v) { return ({ pending: '待审核', approved: '已通过', rejected: '已驳回' })[v] || v || '-' }
async function review(row, decision) {
  const action = decision === 'approved' ? '通过' : '驳回'
  await ElMessageBox.confirm(`确认${action}任务【${row.task_name}】？`, '任务审核')
  const res = await http.post(`/api/tasks/${row.task_id}/review`, { decision })
  if (!res.ok) return ElMessage.error(res.message || '审核失败')
  ElMessage.success(`已${action}`)
  load()
}

async function load() {
  const expected = scope.value
  const token = requestGeneration.next(expected)
  const initial = !loaded.value
  loading.value = initial
  refreshing.value = !initial
  error.value = ''
  try {
    const params = new URLSearchParams({ page: String(page.value), limit: String(limit.value) })
    if (status.value) params.set('status', status.value)
    const res = await http.get(`/api/tasks?${params}`)
    if (!requestGeneration.isCurrent(token, scope.value)) return
    list.value = res.data?.items || []
    total.value = Number(res.data?.total || 0)
    loaded.value = true
  } catch (e) {
    if (!requestGeneration.isCurrent(token, scope.value)) return
    error.value = e?.message || e?.detail || '任务列表加载失败'
  } finally {
    if (requestGeneration.isCurrent(token, scope.value)) {
      loading.value = false
      refreshing.value = false
    }
  }
}
function applyFilters() { page.value = 1; load() }
watch(() => viewScope(store.enterpriseId, store.workspaceId), () => {
  requestGeneration.reset(scope.value, () => { list.value = []; total.value = 0; loaded.value = false; error.value = ''; loading.value = false; refreshing.value = false })
  load()
})
onMounted(load)
</script>
