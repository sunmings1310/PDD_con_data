<template>
  <div class="page-card">
    <div class="toolbar">
      <el-select v-model="status" clearable placeholder="全部状态" style="width:140px" @change="load">
        <el-option label="待下发" value="pending" />
        <el-option label="执行中" value="running" />
        <el-option label="全部完成" value="done" />
        <el-option label="执行失败" value="failed" />
      </el-select>
      <el-button @click="load">刷新</el-button>
      <el-button v-if="store.hasPerm('task:create')" type="primary" @click="$router.push('/tasks/create')">创建任务</el-button>
    </div>
    <el-table :data="list" stripe border @row-click="goDetail">
      <el-table-column prop="task_id" label="任务ID" width="90" />
      <el-table-column prop="task_name" label="任务名称" min-width="160" />
      <el-table-column prop="platform_code" label="平台" width="110" />
      <el-table-column label="状态" width="110">
        <template #default="{ row }">
          <el-tag :type="tagType(row.ui_status)" effect="light">{{ row.ui_status }}</el-tag>
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
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import dayjs from 'dayjs'
import http from '@/api/http'
import { useUserStore } from '@/stores/user'

const store = useUserStore()
const router = useRouter()
const list = ref([])
const status = ref('')

function fmt(v) { return v ? dayjs(v).format('YYYY-MM-DD HH:mm:ss') : '-' }
function countText(row) {
  return `${row.success_count || 0}/${row.fail_count || 0} / ${row.target_count || 0}`
}
function tagType(s) {
  if (s === '全部完成') return 'success'
  if (s === '执行中' || s === '部分成功') return 'warning'
  if (s === '执行失败') return 'danger'
  return 'info'
}
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
  const q = status.value ? `?status=${status.value}` : ''
  const res = await http.get(`/api/tasks${q}`)
  list.value = res.data || []
}
onMounted(load)
</script>
