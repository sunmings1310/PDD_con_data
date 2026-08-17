<template>
  <div class="page-card">
    <div class="toolbar">
      <el-date-picker v-model="range" type="datetimerange" range-separator="至" start-placeholder="开始时间" end-placeholder="结束时间" />
      <el-input v-model="filters.error_code" clearable placeholder="Error code" style="width:150px" />
      <el-input v-model="filters.failure_reason" clearable placeholder="Failure reason" style="width:170px" />
      <el-input v-model="filters.platform" clearable placeholder="平台" style="width:120px" />
      <el-input v-model="filters.product_identity" clearable placeholder="商品标识" style="width:150px" />
      <el-input v-model="filters.task_id" clearable placeholder="Task ID" style="width:110px" />
      <el-input v-model="filters.job_id" clearable placeholder="Job ID" style="width:110px" />
      <el-input v-model="filters.parser_version" clearable placeholder="Parser version" style="width:150px" />
      <el-input v-model="filters.quality_rules_version" clearable placeholder="Rules version" style="width:150px" />
      <el-button type="primary" @click="search">查询</el-button>
      <el-button @click="reset">重置</el-button>
    </div>

    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false">
      <template #default><el-button link type="primary" @click="load">重试</el-button></template>
    </el-alert>
    <el-table v-loading="loading" :data="items" border stripe @row-click="openDetail">
      <template #empty><el-empty :description="loading ? '正在加载' : '没有匹配的 Quarantine 记录'" /></template>
      <el-table-column prop="quarantine_id" label="ID" width="90" />
      <el-table-column label="时间" width="175"><template #default="{row}">{{ fmt(row.collected_at || row.create_time) }}</template></el-table-column>
      <el-table-column prop="platform" label="平台" width="100"><template #default="{row}">{{ row.platform || row.platform_code || '-' }}</template></el-table-column>
      <el-table-column label="商品标识" min-width="150" show-overflow-tooltip><template #default="{row}">{{ productIdentity(row) }}</template></el-table-column>
      <el-table-column prop="failure_reason" label="隔离原因" min-width="210" show-overflow-tooltip />
      <el-table-column label="Error codes" min-width="170" show-overflow-tooltip><template #default="{row}">{{ join(row.error_codes || row.error_codes_json) }}</template></el-table-column>
      <el-table-column label="Task / Job" width="150"><template #default="{row}"><el-link v-if="row.task_id" type="primary" @click.stop="$router.push(`/tasks/${row.task_id}/trace`)">T#{{ row.task_id }}</el-link><span v-if="row.job_id"> / J#{{ row.job_id }}</span></template></el-table-column>
      <el-table-column prop="parser_version" label="Parser" width="120" />
      <el-table-column prop="quality_rules_version" label="Rules" width="120" />
      <el-table-column label="状态" width="90"><template #default="{row}"><el-tag type="danger">{{ row.status || 'open' }}</el-tag></template></el-table-column>
    </el-table>
    <el-pagination class="pager" background layout="total, sizes, prev, pager, next" :total="total" :current-page="page" :page-size="limit" :page-sizes="[20,50,100]" @update:current-page="changePage" @update:page-size="changeLimit" />

    <el-drawer v-model="drawer" title="Quarantine 详情" size="62%" destroy-on-close>
      <div v-loading="detailLoading">
        <el-alert v-if="detailError" :title="detailError" type="error" show-icon :closable="false" />
        <template v-else-if="detail">
          <el-descriptions :column="2" border>
            <el-descriptions-item label="Quarantine">#{{ detail.quarantine_id }}</el-descriptions-item>
            <el-descriptions-item label="隔离原因"><el-text type="danger">{{ detail.failure_reason || '-' }}</el-text></el-descriptions-item>
            <el-descriptions-item label="Error codes" :span="2">{{ join(detail.error_codes || detail.error_codes_json) }}</el-descriptions-item>
            <el-descriptions-item label="Product">{{ productIdentity(detail) }}</el-descriptions-item>
            <el-descriptions-item label="Parser / Rules">{{ detail.parser_version || '-' }} / {{ detail.quality_rules_version || '-' }}</el-descriptions-item>
          </el-descriptions>
          <h3 class="section-title block-title">执行关联</h3>
          <el-space wrap>
            <el-button v-if="detail.task_id" link type="primary" @click="$router.push(`/tasks/${detail.task_id}/trace`)">Task #{{ detail.task_id }}</el-button>
            <span>Job #{{ detail.job_id || '-' }}</span><span>Attempt #{{ detail.attempt_id || '-' }}</span><span>Device #{{ detail.device_id || '-' }}</span>
            <el-button v-if="detail.master_product_id" link type="primary" @click="$router.push(`/products/${detail.master_product_id}/timeline`)">Product #{{ detail.master_product_id }}</el-button>
          </el-space>
          <h3 class="section-title block-title">QualityGate</h3>
          <pre>{{ pretty(detail.quality_result || detail.quality_gate) }}</pre>
          <h3 class="section-title block-title">字段来源 / 证据</h3>
          <pre>{{ pretty(detail.field_sources || detail.provenance || detail.evidence) }}</pre>
          <h3 class="section-title block-title">原始数据引用</h3>
          <pre>{{ pretty(detail.raw_reference || detail.raw_collection || { raw_id: detail.raw_id, request_key: detail.raw_request_key, source_type: detail.source_type, payload_sha256: detail.payload_sha256, collected_at: detail.raw_collected_at, raw_data: detail.raw_data }) }}</pre>
        </template>
        <el-empty v-else-if="!detailLoading" description="详情不存在" />
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import dayjs from 'dayjs'
import http from '@/api/http'

const items = ref([]); const total = ref(0); const page = ref(1); const limit = ref(20)
const route = useRoute()
const loading = ref(false); const error = ref(''); const range = ref([])
const drawer = ref(false); const detail = ref(null); const detailLoading = ref(false); const detailError = ref('')
const filters = reactive({ error_code:'', failure_reason:'', platform:'', product_identity:'', task_id:'', job_id:'', parser_version:'', quality_rules_version:'' })
function fmt(v){ return v ? dayjs(v).format('YYYY-MM-DD HH:mm:ss') : '-' }
function parse(v){ if(Array.isArray(v)) return v; if(!v) return []; try{return JSON.parse(v)}catch{return [v]} }
function join(v){ return parse(v).join(', ') || '-' }
function pretty(v){ if(v===undefined || v===null) return '-'; if(typeof v==='string'){try{return JSON.stringify(JSON.parse(v),null,2)}catch{return v}} return JSON.stringify(v,null,2) }
function productIdentity(row){ return row.product_identity || row.platform_product_id || row.item_id || '-' }
function params(){ const p={page:page.value,limit:limit.value}; Object.entries(filters).forEach(([k,v])=>{if(v!=='')p[k]=v}); if(range.value?.length){p.start_at=dayjs(range.value[0]).toISOString();p.end_at=dayjs(range.value[1]).toISOString()} return p }
async function load(){ loading.value=true; error.value=''; try{const res=await http.get('/api/management/quarantines',{params:params()}); items.value=res.data?.items||[];total.value=Number(res.data?.total||0);page.value=Number(res.data?.page||page.value);limit.value=Number(res.data?.limit||limit.value)}catch(e){items.value=[];total.value=0;error.value=e.response?.data?.detail||e.message||'加载 Quarantine 失败'}finally{loading.value=false} }
function search(){page.value=1;load()} function reset(){Object.keys(filters).forEach(k=>filters[k]='');range.value=[];search()}
function changePage(v){page.value=v;load()} function changeLimit(v){limit.value=v;page.value=1;load()}
async function openDetail(row){drawer.value=true;detail.value=null;detailError.value='';detailLoading.value=true;try{const res=await http.get(`/api/management/quarantines/${row.quarantine_id}`);detail.value=res.data}catch(e){detailError.value=e.response?.data?.detail||e.message||'加载详情失败'}finally{detailLoading.value=false}}
onMounted(()=>{Object.keys(filters).forEach(k=>{if(route.query[k]!==undefined)filters[k]=String(route.query[k])});load()})
</script>
<style scoped>.pager{margin-top:16px;justify-content:flex-end}.block-title{margin-top:22px}pre{white-space:pre-wrap;word-break:break-word;background:#f7f8fa;padding:12px;border-radius:4px}</style>
