<template>
  <div class="page-card">
    <h2 class="page-title">创建采集任务</h2>
    <el-form label-width="140px" style="max-width:960px">
      <el-form-item label="任务名称"><el-input v-model="form.task_name" placeholder="如：感冒灵批量采集" /></el-form-item>
      <el-form-item label="任务类型"><el-radio-group v-model="form.task_type"><el-radio value="collect">采集</el-radio><el-radio value="nurture">养号</el-radio></el-radio-group></el-form-item>
      <el-form-item label="所属平台"><el-select v-model="form.platform_code" style="width:220px"><el-option v-for="p in enabledPlatforms" :key="p.platform_code" :label="p.platform_name" :value="p.platform_code" /></el-select></el-form-item>
      <el-form-item label="分配设备"><el-select v-model="form.device_id" clearable placeholder="自动分配在线设备" style="width:320px"><el-option v-for="d in devices" :key="d.device_id" :label="`${d.device_name || d.device_key}（${d.ui_status}）`" :value="d.device_id" /></el-select></el-form-item>
      <el-form-item v-if="form.task_type === 'nurture'" label="养护账号"><el-select v-model="form.account_id" placeholder="选择已绑定账号" style="width:320px"><el-option v-for="a in accounts" :key="a.account_id" :label="`${a.account_name}（${a.platform_code}）`" :value="a.account_id" /></el-select></el-form-item>
      <el-form-item label="优先级"><el-input-number v-model="form.priority" :min="1" :max="10" /></el-form-item>
      <el-form-item label="数据来源"><el-radio-group v-model="source"><el-radio value="manual">手动粘贴链接/PS短码/关键词</el-radio><el-radio value="excel">Excel 导入创建</el-radio></el-radio-group></el-form-item>
      <el-form-item v-if="source === 'manual'" label="链接/关键词"><el-input v-model="form.keywordsText" type="textarea" :rows="8" placeholder="每行一条：商品链接 / PS短码 / 关键词" /></el-form-item>
      <el-form-item v-else label="Excel 导入"><div class="form-hint">Excel 只提供可审核的候选行；最终目标、设备、账号、节奏与异常策略均由本页统一提交。</div></el-form-item>

      <el-divider content-position="left">统一采集配置</el-divider>
      <el-form-item label="综合前 N 个"><el-input-number v-model="form.max_detail" :min="1" :max="30" /></el-form-item>
      <el-form-item label="额外排序"><el-checkbox v-model="form.enable_price_sort">价格排序第1个</el-checkbox><el-checkbox v-model="form.enable_sales_sort">销量排序第1个</el-checkbox></el-form-item>
      <el-form-item label="操作停顿(秒)"><el-input-number v-model="form.delay_min_sec" :min="1" :max="60" @change="normalizeRange" /><span class="range-separator">~</span><el-input-number v-model="form.delay_max_sec" :min="1" :max="120" @change="normalizeRange" /></el-form-item>
      <el-form-item label="访问节奏"><el-radio-group v-model="form.pace_mode" @change="applyPacePreset"><el-radio-button value="steady">稳健</el-radio-button><el-radio-button value="balanced">均衡</el-radio-button><el-radio-button value="fast">快速</el-radio-button><el-radio-button value="custom">自定义</el-radio-button></el-radio-group></el-form-item>
      <el-form-item label="商品访问间隔"><el-input-number v-model="form.item_gap_min_sec" :min="1" :max="180" @change="normalizeRange" /><span class="range-separator">~</span><el-input-number v-model="form.item_gap_max_sec" :min="1" :max="300" @change="normalizeRange" /></el-form-item>
      <el-form-item label="分批冷却">每采集 <el-input-number v-model="form.batch_size" :min="1" :max="50" class="compact-number" /> 个商品，冷却 <el-input-number v-model="form.batch_cooldown_sec" :min="0" :max="900" class="compact-number" /> 秒</el-form-item>
      <el-form-item label="繁忙与异常"><el-select v-model="form.busy_response" style="width:220px"><el-option label="冷却后自动重试" value="retry" /><el-option label="跳过当前商品" value="skip" /><el-option label="停止本次任务" value="stop" /></el-select><span class="form-hint inline-hint">重试 {{ form.busy_retry_count }} 次；风险冷却 {{ form.risk_cooldown_sec }} 秒；连续异常 {{ form.anomaly_stop_threshold }} 次终止。</span></el-form-item>

      <template v-if="source === 'excel'"><ExcelMatch embedded mode="task-import" :platform-code="form.platform_code" @draft-rows="setExcelRows" /></template>
      <el-divider content-position="left">审核摘要</el-divider>
      <el-alert :title="reviewTitle" :type="review.ready ? 'info' : 'warning'" :closable="false" show-icon />
      <el-alert v-if="submissionError" :title="submissionError" type="error" :closable="false" show-icon style="margin-top:12px"><template #default><el-button link type="primary" :loading="loading" @click="submit">使用原提交重试</el-button></template></el-alert>
      <el-table v-if="draftRows.length" :data="draftRows" row-key="row_id" size="small" border style="margin:14px 0">
        <el-table-column prop="source_row_index" label="行" width="64" />
        <el-table-column prop="normalized_value" label="输入/目标" min-width="180" />
        <el-table-column prop="match_status" label="匹配" width="110" />
        <el-table-column prop="selection_status" label="选择" width="120" />
        <el-table-column label="状态/原因" min-width="200"><template #default="{ row }">{{ row.dispatch_status }}<span v-if="row.error_codes.length"> · {{ row.error_codes.join(', ') }}</span></template></el-table-column>
        <el-table-column label="操作" width="90"><template #default="{ row }"><el-button link :type="row.selection_status === 'excluded' ? 'primary' : 'danger'" @click="toggleRow(row)">{{ row.selection_status === 'excluded' ? '纳入' : '排除' }}</el-button></template></el-table-column>
      </el-table>
      <el-form-item><el-button type="primary" :disabled="!canSubmit" :loading="loading" @click="submit">审核后创建</el-button><el-button @click="$router.back()">取消</el-button></el-form-item>
    </el-form>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRouter } from 'vue-router'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import http from '@/api/http'
import ExcelMatch from '@/views/excel/ExcelMatch.vue'
import { useUserStore } from '@/stores/user'
import { buildCanonicalPayload, canSubmitDraft, newSubmissionId, normalizeExcelRows, normalizeManualRows, prepareDraftRows, reviewDraft, setRowSelection } from '@/utils/taskDraft'

const router = useRouter()
const route = useRoute()
const store = useUserStore()
const platforms = ref([]); const devices = ref([]); const accounts = ref([])
const source = ref('manual'); const loading = ref(false); const submissionError = ref(''); const excelRows = ref([]); const submissionId = ref(newSubmissionId()); const frozenPayload = ref(null)
let routeGeneration = 0
let submitAbort = null
const form = reactive({ task_name: '', task_type: 'collect', platform_code: 'pinduoduo', device_id: null, account_id: null, priority: 5, keywordsText: '', delay_min_sec: 2, delay_max_sec: 5, max_detail: 5, enable_price_sort: false, enable_sales_sort: false, pace_mode: 'steady', item_gap_min_sec: 6, item_gap_max_sec: 10, batch_size: 4, batch_cooldown_sec: 25, busy_response: 'retry', busy_retry_count: 0, busy_cooldown_sec: 15, risk_cooldown_sec: 60, sold_out_stop_threshold: 2, anomaly_stop_threshold: 3 })
const pacePresets = { steady: { item_gap_min_sec: 6, item_gap_max_sec: 10, batch_size: 4, batch_cooldown_sec: 25 }, balanced: { item_gap_min_sec: 4, item_gap_max_sec: 8, batch_size: 5, batch_cooldown_sec: 20 }, fast: { item_gap_min_sec: 2, item_gap_max_sec: 5, batch_size: 8, batch_cooldown_sec: 10 } }
const sourceRows = computed(() => source.value === 'manual' ? normalizeManualRows(form.keywordsText, form.platform_code) : normalizeExcelRows(excelRows.value, form.platform_code))
const draftRows = ref([])
const review = computed(() => reviewDraft(draftRows.value))
const enabledPlatforms = computed(() => platforms.value.filter((platform) => Number(platform.enabled) === 1))
const reviewTitle = computed(() => `有效目标 ${review.value.ready}；错误 ${review.value.invalid}；去重 ${review.value.duplicate}；排除 ${review.value.excluded}；待选择 ${review.value.choice_required}`)
const canSubmit = computed(() => canSubmitDraft(draftRows.value))
function invalidateSubmission() { submitAbort?.abort(); submitAbort = null; loading.value = false; frozenPayload.value = null; submissionError.value = ''; submissionId.value = newSubmissionId() }
function sourceFromQuery(value) { return value === 'excel' ? 'excel' : 'manual' }
function invalidateRoute() { routeGeneration += 1; invalidateSubmission() }
watch(() => route.query.source, (value) => {
  const nextSource = sourceFromQuery(value)
  if (source.value !== nextSource) {
    source.value = nextSource
    invalidateRoute()
  }
}, { immediate: true })
watch(() => route.fullPath, (value, previous) => { if (previous && value !== previous) invalidateRoute() })
watch(sourceRows, (rows) => { draftRows.value = prepareDraftRows(rows, form.platform_code); invalidateSubmission() }, { immediate: true, deep: true })
watch(form, invalidateSubmission, { deep: true })
watch(() => `${store.enterpriseId || ''}:${store.workspaceId || ''}`, () => { routeGeneration += 1; invalidateSubmission() })
function setExcelRows(rows) { excelRows.value = rows }
function applyPacePreset(mode) { if (pacePresets[mode]) Object.assign(form, pacePresets[mode]) }
function normalizeRange() { if (form.delay_max_sec < form.delay_min_sec) form.delay_max_sec = form.delay_min_sec; if (form.item_gap_max_sec < form.item_gap_min_sec) form.item_gap_max_sec = form.item_gap_min_sec }
function config() { normalizeRange(); return { delay_min_sec: form.delay_min_sec, delay_max_sec: form.delay_max_sec, delay_sec: form.delay_min_sec, max_detail: form.max_detail, enable_price_sort: form.enable_price_sort, enable_sales_sort: form.enable_sales_sort, pace_mode: form.pace_mode, item_gap_min_sec: form.item_gap_min_sec, item_gap_max_sec: form.item_gap_max_sec, batch_size: form.batch_size, batch_cooldown_sec: form.batch_cooldown_sec, busy_response: form.busy_response, busy_retry_count: form.busy_retry_count, busy_cooldown_sec: form.busy_cooldown_sec, risk_cooldown_sec: form.risk_cooldown_sec, sold_out_stop_threshold: form.sold_out_stop_threshold, anomaly_stop_threshold: form.anomaly_stop_threshold, image_rule_enabled: false, image_rule_version: 1, account_id: form.task_type === 'nurture' ? form.account_id : null } }
function toggleRow(row) { draftRows.value = setRowSelection(draftRows.value, row.row_id, row.selection_status === 'excluded'); invalidateSubmission() }
async function load() { const [p, d, a] = await Promise.all([http.get('/api/platforms'), http.get('/api/devices'), http.get('/api/accounts')]); platforms.value = p.data || []; if (!enabledPlatforms.value.some((platform) => platform.platform_code === form.platform_code) && enabledPlatforms.value.length) form.platform_code = enabledPlatforms.value[0].platform_code; devices.value = (d.data || []).filter((x) => x.online); accounts.value = a.data || [] }
function nextPayload() { return buildCanonicalPayload({ submissionId: submissionId.value, source: source.value, task: { task_name: form.task_name || `采集任务-${new Date().toLocaleString()}`, task_type: form.task_type, platform_code: form.platform_code, device_id: form.device_id, priority: form.priority, config: config() }, rows: draftRows.value }) }
async function submit() { if (!canSubmit.value) return ElMessage.warning('请修正错误行、完成候选选择或明确排除后再提交'); const requestGeneration = routeGeneration; const controller = new AbortController(); submitAbort = controller; loading.value = true; submissionError.value = ''; try { const payload = frozenPayload.value || nextPayload(); frozenPayload.value = payload; const res = await http.post('/api/tasks', payload, { signal: controller.signal }); if (requestGeneration !== routeGeneration) return; ElMessage.success(`任务已创建 #${res.data.task_id}${res.data.idempotent ? '（已确认重放）' : ''}`); await router.push(`/tasks/${res.data.task_id}`) } catch (error) { if (requestGeneration === routeGeneration) { submissionError.value = '创建未确认：已保留当前审核内容，可使用同一提交重试。'; ElMessage.error(submissionError.value) } throw error } finally { if (requestGeneration === routeGeneration && submitAbort === controller) { loading.value = false; submitAbort = null } } }
onMounted(load)
onBeforeRouteLeave(() => { invalidateRoute(); return true })
onBeforeUnmount(invalidateRoute)
</script>

<style scoped>.form-hint { color:#86909c;font-size:12px;line-height:1.5 }.inline-hint { margin-left:10px }.range-separator { margin:0 8px;color:#86909c }.compact-number { width:110px;margin:0 8px }</style>
