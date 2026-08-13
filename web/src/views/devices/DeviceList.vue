<template>
  <div>
    <div class="page-card">
      <div class="toolbar">
        <el-select v-model="platform" clearable placeholder="全部平台" style="width:160px" @change="load">
          <el-option v-for="p in platforms" :key="p.platform_code" :label="p.platform_name" :value="p.platform_code" />
        </el-select>
        <el-button @click="load">刷新</el-button>
      </div>
      <el-table :data="list" stripe border>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <span class="status-dot" :class="statusClass(row)">{{ row.ui_status }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="device_id" label="设备ID" width="90" />
        <el-table-column label="设备名称" min-width="160">
          <template #default="{ row }">
            <div>{{ row.device_name || row.device_key }}</div>
            <div style="color:#86909C;font-size:12px">{{ row.device_key }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="platform_code" label="平台" width="110" />
        <el-table-column prop="app_version" label="版本" width="100" />
        <el-table-column prop="model" label="型号" width="120" />
        <el-table-column label="绑定运营" width="130">
          <template #default="{ row }">{{ row.owner_real_name || row.owner_username || '未绑定' }}</template>
        </el-table-column>
        <el-table-column label="运行/休息" width="180">
          <template #default="{ row }">
            {{ row.run_state || 'idle' }}
            <div v-if="row.rest_until" style="font-size:12px;color:#86909c">至 {{ fmt(row.rest_until) }}</div>
          </template>
        </el-table-column>
        <el-table-column label="最后心跳" width="170">
          <template #default="{ row }">{{ fmt(row.last_heartbeat) }}</template>
        </el-table-column>
        <el-table-column prop="current_task_id" label="当前任务" width="100" />
        <el-table-column prop="keyword_run_count" label="已执行任务数" width="120" />
        <el-table-column label="操作" width="390" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="$router.push(`/devices/${row.device_id}/live`)">查看实时任务</el-button>
            <el-button v-if="store.hasPerm('device:cast')" link type="primary" @click="$router.push(`/devices/${row.device_id}/cast`)">打开实时投屏</el-button>
            <el-button v-if="store.hasPerm('device:manage')" link type="danger" @click="abort(row)">终止任务</el-button>
            <el-button v-if="store.hasPerm('device:manage')" link type="primary" @click="openBinding(row)">绑定/节奏</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
    <el-dialog v-model="bindingVisible" title="设备绑定与连续运行校验" width="520px">
      <el-form label-width="140px">
        <el-form-item label="绑定运营"><el-select v-model="binding.owner_user_id" clearable style="width:280px"><el-option v-for="u in operators" :key="u.user_id" :label="u.real_name || u.username" :value="u.user_id" /></el-select></el-form-item>
        <el-form-item label="连续运行上限"><el-input-number v-model="binding.max_continuous_min" :min="15" :max="720" /> 分钟</el-form-item>
        <el-form-item label="最少休息"><el-input-number v-model="binding.min_rest_min" :min="5" :max="240" /> 分钟</el-form-item>
      </el-form>
      <template #footer><el-button @click="bindingVisible=false">取消</el-button><el-button type="primary" @click="saveBinding">保存（每人最多2台）</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import dayjs from 'dayjs'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/api/http'
import { useUserStore } from '@/stores/user'

const store = useUserStore()
const list = ref([])
const platforms = ref([])
const platform = ref('')
const operators = ref([])
const bindingVisible = ref(false)
const binding = ref({ device_id: null, owner_user_id: null, max_continuous_min: 120, min_rest_min: 30 })

function fmt(v) {
  return v ? dayjs(v).format('YYYY-MM-DD HH:mm:ss') : '-'
}
function statusClass(row) {
  if (row.ui_status === '采集中') return 'busy'
  if (row.ui_status === '空闲') return 'idle'
  if (row.ui_status === '休息中') return 'busy'
  if (row.ui_status === '异常') return 'error'
  return 'offline'
}

async function openBinding(row) {
  const res = await http.get('/api/accounts/operators')
  operators.value = res.data || []
  binding.value = { device_id: row.device_id, owner_user_id: row.owner_user_id || null, max_continuous_min: row.max_continuous_min || 120, min_rest_min: row.min_rest_min || 30 }
  bindingVisible.value = true
}
async function saveBinding() {
  const res = await http.put(`/api/devices/${binding.value.device_id}/binding`, binding.value)
  if (!res.ok) return ElMessage.error(res.message || '保存失败')
  ElMessage.success(res.message || '已保存')
  bindingVisible.value = false
  load()
}

async function load() {
  const q = platform.value ? `?platform_code=${platform.value}` : ''
  const [d, p] = await Promise.all([
    http.get(`/api/devices${q}`),
    http.get('/api/platforms'),
  ])
  list.value = d.data || []
  platforms.value = p.data || []
}

async function abort(row) {
  await ElMessageBox.confirm(`确认终止设备【${row.device_name || row.device_key}】当前任务？`, '提示', { type: 'warning' })
  await http.post(`/api/devices/${row.device_id}/abort-task`)
  ElMessage.success('已终止')
  load()
}

onMounted(load)
</script>
