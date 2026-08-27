<template>
  <div>
    <div class="page-card">
      <div class="toolbar">
        <el-button @click="$router.push(`/tasks/${taskId}`)">返回任务</el-button>
        <el-button @click="$router.push(`/tasks/${taskId}/trace`)">执行轨迹</el-button>
        <el-button type="primary" @click="load">刷新证据</el-button>
      </div>
      <el-alert v-if="error" :title="error" type="error" show-icon :closable="false">
        <template #default><el-button link type="primary" @click="load">重试</el-button></template>
      </el-alert>
      <div v-loading="loading">
        <el-empty v-if="!loading && !error && !detail" description="该 Task 中不存在此资源，或当前租户不可见" />
        <template v-else-if="detail">
          <el-descriptions :column="3" border>
            <el-descriptions-item label="Task">#{{ detail.task_id }}</el-descriptions-item>
            <el-descriptions-item label="资源类型">{{ resourceLabel(detail.resource_kind) }}</el-descriptions-item>
            <el-descriptions-item label="权威资源 ID">#{{ detail.resource_id }}</el-descriptions-item>
          </el-descriptions>
        </template>
      </div>
    </div>

    <div v-if="detail" class="page-card">
      <h3 class="section-title">资源链</h3>
      <el-table :data="resourceRows" border>
        <el-table-column prop="label" label="资源" width="170" />
        <el-table-column label="状态" width="130">
          <template #default="{ row }">
            <el-tag :type="row.available ? 'success' : 'info'">
              {{ row.available ? 'available' : 'unavailable' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="资源 ID" width="140">
          <template #default="{ row }">{{ row.id === null ? '-' : `#${row.id}` }}</template>
        </el-table-column>
        <el-table-column label="说明" min-width="240">
          <template #default="{ row }">{{ row.reason || '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="110">
          <template #default="{ row }">
            <el-button v-if="row.available && row.routeKind" link type="primary" @click="openResource(row.routeKind, row.id)">查看</el-button>
            <span v-else>-</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div v-if="detail" class="page-card">
      <h3 class="section-title">只读证据</h3>
      <el-alert title="Raw、Quality、Snapshot 与 Quarantine 均为只读事实；本页面不提供修改操作。" type="info" show-icon :closable="false" />
      <pre>{{ pretty(detail.details) }}</pre>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import http from '@/api/http'

const route = useRoute()
const router = useRouter()
const detail = ref(null)
const loading = ref(false)
const error = ref('')
const taskId = computed(() => String(route.params.taskId))
const routeKinds = { snapshot: 'snapshot', raw: 'raw', quality: 'quality', quarantine: 'quarantine' }
const labels = {
  snapshot: 'Snapshot', master_product: 'Master Product', enterprise_product: 'Enterprise Product',
  product: '资料库商品', raw: 'Raw Evidence', quality: 'Quality Result', quarantine: 'Quarantine',
}
const resourceRows = computed(() => Object.entries(detail.value?.resources || {}).map(([key, value]) => ({
  key,
  label: labels[key] || key,
  id: value?.resource_id ?? null,
  available: value?.availability === 'available',
  reason: value?.reason || '',
  routeKind: routeKinds[key] || '',
})))

function resourceLabel(kind) { return labels[kind] || kind || '-' }
function pretty(value) { return value === undefined || value === null ? '-' : JSON.stringify(value, null, 2) }
function requestError(e) {
  if (e.response?.status === 403) return '无权限查看该 Task 证据（403）'
  if (e.response?.status === 404 || e.data?.error_code === 'NOT_FOUND' || e.response?.data?.data?.error_code === 'NOT_FOUND') {
    return '资源不存在，或不属于当前 Task / 租户'
  }
  return e.response?.data?.detail || e.message || '加载证据失败'
}
function openResource(kind, id) {
  if (!kind || id === null || id === undefined) return
  router.push(`/tasks/${taskId.value}/results/${kind}/${id}`)
}
async function load() {
  const expected = `${route.params.taskId}:${route.params.resourceKind}:${route.params.resourceId}`
  loading.value = true
  error.value = ''
  detail.value = null
  try {
    const res = await http.get(
      `/api/management/tasks/${route.params.taskId}/results/${route.params.resourceKind}/${route.params.resourceId}`,
    )
    if (expected !== `${route.params.taskId}:${route.params.resourceKind}:${route.params.resourceId}`) return
    detail.value = res.data || null
  } catch (e) {
    if (expected !== `${route.params.taskId}:${route.params.resourceKind}:${route.params.resourceId}`) return
    detail.value = null
    error.value = requestError(e)
  } finally {
    if (expected === `${route.params.taskId}:${route.params.resourceKind}:${route.params.resourceId}`) loading.value = false
  }
}

watch(() => [route.params.taskId, route.params.resourceKind, route.params.resourceId], load, { immediate: true })
</script>

<style scoped>
.page-card pre { white-space: pre-wrap; word-break: break-word; background: #f7f8fa; padding: 12px; border-radius: 4px; }
</style>
