<template>
  <div class="page-card">
    <div class="toolbar">
      <el-button @click="$router.back()">返回</el-button>
      <el-button type="primary" @click="load">刷新</el-button>
      <span style="color:#86909C">设备 #{{ id }} 实时任务（WebSocket 推送日志）</span>
    </div>
    <el-descriptions :column="3" border>
      <el-descriptions-item label="当前任务">{{ device?.current_task_id || '-' }}</el-descriptions-item>
      <el-descriptions-item label="状态">{{ device?.ui_status || '-' }}</el-descriptions-item>
      <el-descriptions-item label="心跳">{{ fmt(device?.last_heartbeat) }}</el-descriptions-item>
    </el-descriptions>

    <template v-if="task">
      <h3 class="section-title" style="margin-top:16px">任务进度</h3>
      <el-progress
        :percentage="percent"
        :status="task.status === 'failed' ? 'exception' : task.status === 'done' ? 'success' : undefined"
      />
      <p style="margin:8px 0 16px;color:#4E5969">
        成功 {{ task.success_count || 0 }} / 失败 {{ task.fail_count || 0 }} / 目标 {{ task.target_count || 0 }}
      </p>
      <el-table :data="logs" height="360" border>
        <el-table-column prop="create_time" label="时间" width="180">
          <template #default="{ row }">{{ fmt(row.create_time) }}</template>
        </el-table-column>
        <el-table-column prop="level_code" label="级别" width="90" />
        <el-table-column prop="message" label="日志" />
      </el-table>
    </template>
    <el-empty v-else description="当前无执行中任务" />
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import dayjs from 'dayjs'
import http from '@/api/http'

const route = useRoute()
const id = route.params.id
const device = ref(null)
const task = ref(null)
const logs = ref([])
let ws
let timer

const percent = computed(() => {
  const t = task.value
  if (!t || !t.target_count) return 0
  const done = (t.success_count || 0) + (t.fail_count || 0)
  return Math.min(100, Math.round((done / t.target_count) * 100))
})

function fmt(v) {
  return v ? dayjs(v).format('YYYY-MM-DD HH:mm:ss') : '-'
}

async function load() {
  const dres = await http.get('/api/devices')
  device.value = (dres.data || []).find((x) => String(x.device_id) === String(id))
  if (device.value?.current_task_id) {
    const tres = await http.get(`/api/tasks/${device.value.current_task_id}`)
    task.value = tres.data
    logs.value = tres.data?.logs || []
  } else {
    task.value = null
    logs.value = []
  }
}

function connectWs() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  ws = new WebSocket(`${proto}://${location.host}/ws/realtime`)
  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data)
      if (msg.event === 'task_log' && task.value && msg.data.task_id === task.value.task_id) {
        logs.value = [
          { create_time: new Date().toISOString(), level_code: msg.data.level, message: msg.data.message },
          ...logs.value,
        ].slice(0, 200)
      }
    } catch { /* ignore */ }
  }
}

onMounted(() => {
  load()
  connectWs()
  timer = setInterval(load, 8000)
})
onUnmounted(() => {
  clearInterval(timer)
  ws?.close()
})
</script>
