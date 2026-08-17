<template>
  <div class="page-card">
    <div class="toolbar">
      <el-button @click="$router.back()">返回</el-button>
      <el-button type="primary" :loading="starting" @click="startCast">发起投屏</el-button>
      <el-button type="danger" plain @click="stopCast">停止投屏</el-button>
      <el-button @click="screenshot">一键截图</el-button>
      <el-button @click="saveLogs">保存现场日志</el-button>
      <el-tag :type="streaming ? 'success' : 'info'">{{ streaming ? '推流中' : '未推流' }}</el-tag>
    </div>
    <div class="cast-layout">
      <div class="phone-pane">
        <div class="phone-frame" ref="frameRef">
          <img v-if="frameUrl" :src="frameUrl" class="frame-img" alt="投屏画面" />
          <div v-else class="placeholder">
            <p>等待手机推流…</p>
            <p class="hint">点击「发起投屏」后，APP 将自动点击系统「立即开始」并上行画面</p>
          </div>
          <canvas ref="canvasRef" class="hidden-canvas" />
        </div>
      </div>
      <div class="log-pane">
        <h3 class="section-title">实时任务日志</h3>
        <el-scrollbar height="560px">
          <div v-for="(l, i) in logs" :key="i" class="log-line">
            <span class="t">{{ l.t }}</span>{{ l.msg }}
          </div>
        </el-scrollbar>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import dayjs from 'dayjs'
import { ElMessage } from 'element-plus'
import http from '@/api/http'

const route = useRoute()
const streaming = ref(false)
const starting = ref(false)
const logs = ref([])
const frameUrl = ref('')
const frameRef = ref()
const canvasRef = ref()
let ws
let timer
let objectUrl

function pushLog(msg) {
  logs.value.unshift({ t: dayjs().format('HH:mm:ss'), msg })
}

function connectView() {
  ws?.close()
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const params = new URLSearchParams({
    token: localStorage.getItem('sjzq_token') || '',
    enterprise_id: localStorage.getItem('sjzq_enterprise_id') || '',
    workspace_id: localStorage.getItem('sjzq_workspace_id') || '',
  })
  ws = new WebSocket(`${proto}://${location.host}/ws/cast/view/${route.params.id}?${params}`)
  ws.binaryType = 'arraybuffer'
  ws.onopen = () => pushLog('已连接投屏观看通道')
  ws.onclose = () => {
    streaming.value = false
    pushLog('观看通道已断开')
  }
  ws.onmessage = (ev) => {
    if (typeof ev.data === 'string') {
      try {
        const msg = JSON.parse(ev.data)
        if (msg.type === 'hello') {
          pushLog(msg.publishing ? '设备已在推流' : '等待设备推流')
        } else if (msg.type === 'stopped') {
          streaming.value = false
          pushLog('投屏已停止')
        }
      } catch { /* ignore */ }
      return
    }
    const blob = new Blob([ev.data], { type: 'image/jpeg' })
    if (objectUrl) URL.revokeObjectURL(objectUrl)
    objectUrl = URL.createObjectURL(blob)
    frameUrl.value = objectUrl
    streaming.value = true
  }
}

async function startCast() {
  starting.value = true
  try {
    await http.post(`/api/cast/${route.params.id}/start`)
    pushLog('已请求设备开始投屏（APP 将自动点确认）')
    ElMessage.success('已下发投屏请求')
    connectView()
  } finally {
    starting.value = false
  }
}

async function stopCast() {
  await http.post(`/api/cast/${route.params.id}/stop`)
  ws?.close()
  streaming.value = false
  pushLog('已停止投屏')
}

function screenshot() {
  if (!frameUrl.value) {
    ElMessage.warning('暂无画面')
    return
  }
  const a = document.createElement('a')
  a.href = frameUrl.value
  a.download = `cast_${route.params.id}_${Date.now()}.jpg`
  a.click()
  pushLog('已保存截图')
}

function saveLogs() {
  const text = logs.value.map((l) => `[${l.t}] ${l.msg}`).join('\n')
  const blob = new Blob([text || '暂无日志'], { type: 'text/plain;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `device_${route.params.id}_logs.txt`
  a.click()
}

async function loadTaskLogs() {
  try {
    const dres = await http.get('/api/devices')
    const device = (dres.data || []).find((x) => String(x.device_id) === String(route.params.id))
    if (!device?.current_task_id) return
    const tres = await http.get(`/api/tasks/${device.current_task_id}`)
    const arr = tres.data?.logs || []
    const mapped = arr.slice(0, 40).map((x) => ({
      t: x.create_time ? dayjs(x.create_time).format('HH:mm:ss') : '--:--:--',
      msg: x.message,
    }))
    // 保留投屏相关日志在前
    const castLogs = logs.value.filter((l) => !mapped.some((m) => m.msg === l.msg))
    logs.value = [...castLogs.slice(0, 20), ...mapped].slice(0, 100)
  } catch { /* ignore */ }
}

onMounted(() => {
  pushLog('进入投屏监控页')
  connectView()
  loadTaskLogs()
  timer = setInterval(loadTaskLogs, 5000)
})
onUnmounted(() => {
  clearInterval(timer)
  ws?.close()
  if (objectUrl) URL.revokeObjectURL(objectUrl)
})
</script>

<style scoped>
.cast-layout {
  display: grid;
  grid-template-columns: 420px 1fr;
  gap: 16px;
}
.phone-frame {
  width: 100%;
  aspect-ratio: 9 / 16;
  background: #0b1220;
  border-radius: 6px;
  border: 1px solid var(--sjzq-border);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  color: #fff;
  position: relative;
}
.frame-img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  background: #000;
}
.placeholder { text-align: center; padding: 20px; }
.hint { color: #86909c; font-size: 12px; margin-bottom: 12px; }
.log-pane {
  border: 1px solid var(--sjzq-border);
  border-radius: 6px;
  padding: 12px;
  background: #fff;
}
.log-line {
  font-size: 12px;
  padding: 6px 0;
  border-bottom: 1px dashed #f0f0f0;
  color: #4e5969;
}
.log-line .t { color: #86909c; margin-right: 8px; }
.hidden-canvas { display: none; }
@media (max-width: 960px) {
  .cast-layout { grid-template-columns: 1fr; }
}
</style>
