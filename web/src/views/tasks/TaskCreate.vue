<template>
  <div class="page-card">
    <h2 class="page-title">创建采集任务</h2>
    <el-form label-width="140px" style="max-width:860px">
      <el-form-item label="任务名称">
        <el-input v-model="form.task_name" placeholder="如：感冒灵批量采集" />
      </el-form-item>
      <el-form-item label="任务类型">
        <el-radio-group v-model="form.task_type">
          <el-radio value="collect">采集</el-radio>
          <el-radio value="nurture">养号</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="所属平台">
        <el-select v-model="form.platform_code" style="width:220px">
          <el-option v-for="p in platforms" :key="p.platform_code" :label="`${p.platform_name}${p.enabled ? '' : '（预留）'}`" :value="p.platform_code" />
        </el-select>
      </el-form-item>
      <el-form-item label="分配设备">
        <el-select v-model="form.device_id" clearable placeholder="自动分配在线设备" style="width:320px">
          <el-option v-for="d in devices" :key="d.device_id" :label="`${d.device_name || d.device_key}（${d.ui_status}）`" :value="d.device_id" />
        </el-select>
      </el-form-item>
      <el-form-item v-if="form.task_type === 'nurture'" label="养护账号">
        <el-select v-model="form.account_id" placeholder="选择已绑定账号" style="width:320px">
          <el-option v-for="a in accounts" :key="a.account_id" :label="`${a.account_name}（${a.platform_code}）`" :value="a.account_id" />
        </el-select>
        <div class="form-hint">养护任务仅模拟搜索和浏览，不采集商品入库。</div>
      </el-form-item>
      <el-form-item label="优先级">
        <el-input-number v-model="form.priority" :min="1" :max="10" />
      </el-form-item>
      <el-form-item label="数据来源">
        <el-radio-group v-model="source">
          <el-radio value="manual">手动粘贴链接/PS短码/关键词</el-radio>
          <el-radio value="excel">Excel 导入创建</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item v-if="source === 'manual'" label="链接/关键词">
        <el-input v-model="form.keywordsText" type="textarea" :rows="8" placeholder="每行一条：商品链接 / PS短码 / 关键词" />
      </el-form-item>
      <el-form-item v-else label="上传清单">
        <div class="form-hint">Excel匹配、结果预览、批量导出及安卓补采已整合在本页下方。</div>
      </el-form-item>

      <template v-if="source === 'manual'">
      <el-divider content-position="left">采集范围（下发到 APP）</el-divider>
      <el-form-item label="综合前 N 个">
        <el-input-number v-model="form.max_detail" :min="1" :max="30" />
      </el-form-item>
      <el-form-item label="额外排序">
        <el-checkbox v-model="form.enable_price_sort">价格排序第1个</el-checkbox>
        <el-checkbox v-model="form.enable_sales_sort">销量排序第1个</el-checkbox>
      </el-form-item>
      <el-form-item label="操作停顿(秒)">
        <el-input-number v-model="form.delay_min_sec" :min="1" :max="60" @change="normalizeRange" />
        <span style="margin:0 8px;color:#86909C">~</span>
        <el-input-number v-model="form.delay_max_sec" :min="1" :max="120" @change="normalizeRange" />
        <div style="color:#86909C;font-size:12px;margin-top:6px">
          APP 每次操作前在此区间内随机等待（含停顿抖动）
        </div>
      </el-form-item>
      <el-form-item label="拟人强度">
        <el-radio-group v-model="form.human_level">
          <el-radio value="gentle">轻（更快）</el-radio>
          <el-radio value="normal">中</el-radio>
          <el-radio value="strict">强（更像真人）</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="拟人动作">
        <el-checkbox v-model="form.enable_human_gestures">额外拟人动作（随机回滑、短暂浏览、走神停顿）</el-checkbox>
      </el-form-item>

      <el-divider content-position="left">访问节奏</el-divider>
      <div class="strategy-panel">
        <el-form-item label="节奏方案">
          <el-radio-group v-model="form.pace_mode" @change="applyPacePreset">
            <el-radio-button value="steady">稳健</el-radio-button>
            <el-radio-button value="balanced">均衡</el-radio-button>
            <el-radio-button value="fast">快速</el-radio-button>
            <el-radio-button value="custom">自定义</el-radio-button>
          </el-radio-group>
          <div class="form-hint">商品访问间隔独立于页面内操作停顿；每批完成后统一冷却。</div>
        </el-form-item>
        <el-form-item label="商品访问间隔">
          <el-input-number v-model="form.item_gap_min_sec" :min="1" :max="180" @change="normalizeRange" />
          <span class="range-separator">~</span>
          <el-input-number v-model="form.item_gap_max_sec" :min="1" :max="300" @change="normalizeRange" />
          <span class="unit">秒</span>
        </el-form-item>
        <el-form-item label="分批冷却">
          每采集
          <el-input-number v-model="form.batch_size" :min="1" :max="50" class="compact-number" />
          个商品，冷却
          <el-input-number v-model="form.batch_cooldown_sec" :min="0" :max="900" class="compact-number" />
          秒
        </el-form-item>
      </div>

      <el-divider content-position="left">繁忙与异常回复</el-divider>
      <div class="strategy-panel">
        <el-form-item label="检测到繁忙">
          <el-select v-model="form.busy_response" style="width:260px">
            <el-option label="冷却后自动重试" value="retry" />
            <el-option label="跳过当前商品" value="skip" />
            <el-option label="停止本次任务" value="stop" />
          </el-select>
          <div class="form-hint">识别“系统繁忙、访问频繁、请稍后再试”等页面后执行所选动作。</div>
        </el-form-item>
        <el-form-item v-if="form.busy_response === 'retry'" label="重试设置">
          自动重试
          <el-input-number v-model="form.busy_retry_count" :min="0" :max="5" class="compact-number" />
          次，首次冷却
          <el-input-number v-model="form.busy_cooldown_sec" :min="5" :max="900" class="compact-number" />
          秒
        </el-form-item>
        <el-form-item label="疑似风控冷却">
          <el-input-number v-model="form.risk_cooldown_sec" :min="10" :max="1800" />
          <span class="unit">秒</span>
          <div class="form-hint">自动重试疑似风控页面时使用独立冷却时间。</div>
        </el-form-item>
        <el-form-item label="连续售罄停止">
          <el-input-number v-model="form.sold_out_stop_threshold" :min="0" :max="20" />
          <span class="unit">个（0 表示不停）</span>
        </el-form-item>
        <el-form-item label="连续异常终止">
          <el-input-number v-model="form.anomaly_stop_threshold" :min="0" :max="20" />
          <span class="unit">次（默认 3，0 表示不自动终止）</span>
          <div class="form-hint">连续动作异常时自动截图并记录日志；达到阈值后终止任务。</div>
        </el-form-item>
      </div>

      <el-alert
        title="图片选用规则暂未启用"
        type="info"
        :closable="false"
        description="任务配置已预留图片规则版本字段，当前仍按既有方式采图，后续可兼容水印、店铺词和禁用词筛选。"
        show-icon
        style="margin:18px 0"
      />

      <el-form-item>
        <el-button type="primary" :loading="loading" @click="submit">创建并下发</el-button>
        <el-button @click="$router.back()">取消</el-button>
      </el-form-item>
      </template>
    </el-form>
    <ExcelMatch v-if="source === 'excel'" embedded />
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import http from '@/api/http'
import ExcelMatch from '@/views/excel/ExcelMatch.vue'

const router = useRouter()
const platforms = ref([])
const devices = ref([])
const accounts = ref([])
const source = ref('manual')
const loading = ref(false)
const form = reactive({
  task_name: '',
  task_type: 'collect',
  platform_code: 'pinduoduo',
  device_id: null,
  account_id: null,
  priority: 5,
  keywordsText: '',
  delay_min_sec: 2,
  delay_max_sec: 5,
  max_detail: 5,
  enable_price_sort: false,
  enable_sales_sort: false,
  human_level: 'strict',
  enable_human_gestures: true,
  pace_mode: 'steady',
  item_gap_min_sec: 6,
  item_gap_max_sec: 10,
  batch_size: 4,
  batch_cooldown_sec: 25,
  busy_response: 'retry',
  busy_retry_count: 0,
  busy_cooldown_sec: 15,
  risk_cooldown_sec: 60,
  sold_out_stop_threshold: 2,
  anomaly_stop_threshold: 3,
})

const pacePresets = {
  steady: { item_gap_min_sec: 6, item_gap_max_sec: 10, batch_size: 4, batch_cooldown_sec: 25 },
  balanced: { item_gap_min_sec: 4, item_gap_max_sec: 8, batch_size: 5, batch_cooldown_sec: 20 },
  fast: { item_gap_min_sec: 2, item_gap_max_sec: 5, batch_size: 8, batch_cooldown_sec: 10 },
}

function applyPacePreset(mode) {
  const preset = pacePresets[mode]
  if (preset) Object.assign(form, preset)
}

function normalizeRange() {
  if (form.delay_max_sec < form.delay_min_sec) {
    form.delay_max_sec = form.delay_min_sec
  }
  if (form.item_gap_max_sec < form.item_gap_min_sec) {
    form.item_gap_max_sec = form.item_gap_min_sec
  }
}

async function load() {
  const [p, d, a] = await Promise.all([http.get('/api/platforms'), http.get('/api/devices'), http.get('/api/accounts')])
  platforms.value = p.data || []
  devices.value = (d.data || []).filter((x) => x.online)
  accounts.value = a.data || []
}

async function submit() {
  normalizeRange()
  const keywords = form.keywordsText.split(/\r?\n/).map((x) => x.trim()).filter(Boolean)
  if (!keywords.length) {
    ElMessage.warning('请填写采集目标')
    return
  }
  loading.value = true
  try {
    const res = await http.post('/api/tasks', {
      task_name: form.task_name || `采集任务-${new Date().toLocaleString()}`,
      task_type: form.task_type,
      platform_code: form.platform_code,
      device_id: form.device_id,
      priority: form.priority,
      keywords,
      target_count: keywords.length,
      config: {
        delay_min_sec: form.delay_min_sec,
        delay_max_sec: form.delay_max_sec,
        // 兼容旧字段
        delay_sec: form.delay_min_sec,
        max_detail: form.max_detail,
        enable_price_sort: form.enable_price_sort,
        enable_sales_sort: form.enable_sales_sort,
        human_level: form.human_level,
        enable_human_gestures: form.enable_human_gestures,
        pace_mode: form.pace_mode,
        item_gap_min_sec: form.item_gap_min_sec,
        item_gap_max_sec: form.item_gap_max_sec,
        batch_size: form.batch_size,
        batch_cooldown_sec: form.batch_cooldown_sec,
        busy_response: form.busy_response,
        busy_retry_count: form.busy_retry_count,
        busy_cooldown_sec: form.busy_cooldown_sec,
        risk_cooldown_sec: form.risk_cooldown_sec,
        sold_out_stop_threshold: form.sold_out_stop_threshold,
        anomaly_stop_threshold: form.anomaly_stop_threshold,
        image_rule_enabled: false,
        image_rule_version: 1,
        account_id: form.task_type === 'nurture' ? form.account_id : null,
      },
    })
    ElMessage.success(`任务已创建 #${res.data.task_id}`)
    router.push(`/tasks/${res.data.task_id}`)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.strategy-panel {
  margin: -4px 0 18px;
  padding: 18px 18px 2px;
  border: 1px solid #e5e9f2;
  border-radius: 12px;
  background: linear-gradient(135deg, #fbfdff 0%, #f7faff 100%);
}
.form-hint {
  width: 100%;
  margin-top: 6px;
  color: #86909c;
  font-size: 12px;
  line-height: 1.5;
}
.range-separator {
  margin: 0 8px;
  color: #86909c;
}
.unit {
  margin-left: 8px;
  color: #4e5969;
}
.compact-number {
  width: 120px;
  margin: 0 8px;
}
</style>
