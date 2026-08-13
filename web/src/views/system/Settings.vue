<template>
  <div class="page-card">
    <h2 class="page-title">系统设置</h2>
    <el-form label-width="160px" style="max-width:720px">
      <el-form-item label="默认平台">
        <el-select v-model="form.default_platform" style="width:240px">
          <el-option label="拼多多" value="pinduoduo" />
          <el-option label="天猫（预留）" value="tmall" />
          <el-option label="京东（预留）" value="jd" />
          <el-option label="抖音（预留）" value="douyin" />
        </el-select>
      </el-form-item>
      <el-form-item label="全局采集限速(秒)">
        <el-input-number v-model="form.delay_sec" :min="1" :max="60" />
      </el-form-item>
      <el-form-item label="设备心跳超时(秒)">
        <el-input-number v-model="form.heartbeat_timeout" :min="30" :max="600" />
      </el-form-item>
      <el-form-item label="图片存储路径">
        <el-input v-model="form.image_dir" disabled />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="save">保存配置</el-button>
        <span style="margin-left:10px;color:#86909C;font-size:12px">当前以服务端 .env / 运行配置为准，页面配置预留落库</span>
      </el-form-item>
    </el-form>

    <el-divider />
    <h2 class="page-title">App 一键更新</h2>
    <p class="hint">上传 APK 后点击「一键更新」：全部设备停止进行中任务，并在下次心跳自动下载安装。</p>
    <el-form label-width="160px" style="max-width:720px">
      <el-form-item label="选择 APK">
        <input type="file" accept=".apk,application/vnd.android.package-archive" @change="onFile" />
      </el-form-item>
      <el-form-item label="版本号">
        <el-input v-model="ota.version_name" placeholder="如 1.0.24" style="width:200px" />
      </el-form-item>
      <el-form-item label="versionCode">
        <el-input-number v-model="ota.version_code" :min="0" :max="999999" />
      </el-form-item>
      <el-form-item label="当前包">
        <span v-if="status.has_apk">
          已上传 {{ formatSize(status.apk_size) }}
          <a v-if="status.apk_url" :href="status.apk_url" target="_blank" style="margin-left:8px">下载</a>
        </span>
        <span v-else style="color:#86909C">尚未上传</span>
      </el-form-item>
      <el-form-item label="下发状态">
        <span v-if="status.pending">
          待更新设备 {{ status.pending.pending_devices ?? 0 }}，目标 v{{ status.pending.version_name }}
        </span>
        <span v-else style="color:#86909C">无进行中的更新</span>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" :loading="uploading" :disabled="!file" @click="upload">上传 APK</el-button>
        <el-button type="danger" :loading="pushing" :disabled="!status.has_apk" @click="pushUpdate">一键更新全部设备</el-button>
        <el-button @click="loadStatus">刷新状态</el-button>
      </el-form-item>
    </el-form>

    <el-divider />
    <h2 class="page-title">图片清理</h2>
    <p class="hint">OCR 识别已入库本地图片，删除「药品经营许可证」等证照图；新上传也会自动拦截不落库。</p>
    <el-form label-width="160px" style="max-width:720px">
      <el-form-item>
        <el-button type="warning" :loading="purging" @click="purgeLicenses">清理证照图片</el-button>
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/api/http'

const form = reactive({
  default_platform: 'pinduoduo',
  delay_sec: 3,
  heartbeat_timeout: 90,
  image_dir: '',
})

const ota = reactive({ version_name: '', version_code: 0 })
const file = ref(null)
const uploading = ref(false)
const pushing = ref(false)
const purging = ref(false)
const status = reactive({ has_apk: false, apk_size: 0, apk_url: '', pending: null, meta: null })

function formatSize(n) {
  if (!n) return '0B'
  if (n < 1024) return `${n}B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)}KB`
  return `${(n / 1024 / 1024).toFixed(2)}MB`
}

function onFile(e) {
  const f = e.target.files?.[0]
  file.value = f || null
  if (f?.name) {
    const m = f.name.match(/v?(\d+\.\d+\.\d+)/i)
    if (m) ota.version_name = m[1]
  }
}

async function load() {
  const h = await http.get('/api/health')
  form.image_dir = h.image_dir || ''
}

async function loadStatus() {
  try {
    const res = await http.get('/api/ota/status')
    const d = res.data || {}
    status.has_apk = !!d.has_apk
    status.apk_size = d.apk_size || 0
    status.apk_url = d.apk_url || ''
    status.pending = d.pending || null
    status.meta = d.meta || null
    if (!ota.version_name && d.meta?.version_name) ota.version_name = d.meta.version_name
    if (!ota.version_code && d.meta?.version_code) ota.version_code = d.meta.version_code
  } catch (e) {
    /* ignore */
  }
}

function save() {
  ElMessage.success('配置已记录（后续接入 SJZQ_SYS_CONFIG 持久化）')
}

async function upload() {
  if (!file.value) {
    ElMessage.warning('请先选择 APK')
    return
  }
  uploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', file.value)
    fd.append('version_name', ota.version_name || '1.0.0')
    fd.append('version_code', String(ota.version_code || 0))
    const res = await http.post('/api/ota/upload', fd)
    if (res.ok === false) {
      ElMessage.error(res.message || '上传失败')
      return
    }
    ElMessage.success('APK 已上传')
    if (res.data?.version_name) ota.version_name = res.data.version_name
    await loadStatus()
  } catch (e) {
    ElMessage.error(e?.message || '上传失败')
  } finally {
    uploading.value = false
  }
}

async function pushUpdate() {
  try {
    await ElMessageBox.confirm(
      '将停止全部设备进行中的任务，并下发 APK 更新。设备需已开启「允许安装未知应用」。是否继续？',
      '一键更新',
      { type: 'warning' },
    )
  } catch {
    return
  }
  pushing.value = true
  try {
    const res = await http.post('/api/ota/push', {
      version_name: ota.version_name || undefined,
      version_code: ota.version_code || 0,
    })
    if (res.ok === false) {
      ElMessage.error(res.message || '下发失败')
      return
    }
    ElMessage.success(`已下发：设备 ${res.data?.devices ?? 0}，停任务 ${res.data?.aborted_tasks ?? 0}`)
    await loadStatus()
  } catch (e) {
    ElMessage.error(e?.message || '下发失败')
  } finally {
    pushing.value = false
  }
}

async function purgeLicenses() {
  try {
    await ElMessageBox.confirm(
      '将 OCR 扫描已入库本地图片，删除识别为药品经营许可证等证照的文件与库记录。是否继续？',
      '清理证照图片',
      { type: 'warning' },
    )
  } catch {
    return
  }
  purging.value = true
  try {
    const res = await http.post('/api/products/images/purge-licenses?limit=2000')
    if (res.ok === false) {
      ElMessage.error(res.message || '清理失败')
      return
    }
    ElMessage.success(
      `扫描 ${res.data?.scanned ?? 0} 张，删除 ${res.data?.deleted ?? 0} 张证照图`,
    )
  } catch (e) {
    ElMessage.error(e?.message || '清理失败')
  } finally {
    purging.value = false
  }
}

onMounted(async () => {
  await load()
  await loadStatus()
})
</script>

<style scoped>
.hint {
  color: #86909c;
  font-size: 13px;
  margin: 0 0 16px;
  max-width: 720px;
}
</style>
