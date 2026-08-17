<template>
  <div>
    <div class="page-card">
      <div class="toolbar">
        <el-date-picker v-model="range" type="datetimerange" range-separator="至" start-placeholder="开始时间" end-placeholder="结束时间" />
        <el-input v-model="filters.platform" clearable placeholder="平台" style="width:130px" />
        <el-button type="primary" @click="load">刷新指标</el-button>
      </div>
      <el-alert v-if="error" :title="error" type="error" show-icon :closable="false"><template #default><el-button link type="primary" @click="load">重试</el-button></template></el-alert>
      <div v-loading="loading">
        <el-empty v-if="!loading && !error && !hasData" description="当前筛选范围内暂无质量数据" />
        <template v-else-if="hasData">
          <el-row :gutter="12" class="metrics">
            <el-col v-for="card in cards" :key="card.label" :xs="12" :sm="8" :lg="4">
              <el-card shadow="never"><el-statistic :title="card.label" :value="card.value" :suffix="card.suffix" :precision="card.precision" /></el-card>
            </el-col>
          </el-row>
          <el-alert v-for="(alert,idx) in anomalies" :key="idx" class="anomaly" :title="anomalyText(alert)" type="warning" show-icon :closable="false" />
        </template>
      </div>
    </div>
    <el-row v-if="hasData" :gutter="16">
      <el-col :xs="24" :lg="12"><div class="page-card"><h3 class="section-title">Parser 版本质量</h3><metric-table :rows="parserRows" label="Parser version" /></div></el-col>
      <el-col :xs="24" :lg="12"><div class="page-card"><h3 class="section-title">质量规则版本</h3><metric-table :rows="rulesRows" label="Rules version" /></div></el-col>
    </el-row>
    <el-row v-if="hasData" :gutter="16">
      <el-col :xs="24" :lg="12"><div class="page-card"><h3 class="section-title">关键字段缺失率</h3><el-table :data="missingRows" border><template #empty><el-empty description="无字段缺失数据" /></template><el-table-column prop="field" label="字段" /><el-table-column label="缺失数"><template #default="{row}">{{ row.count ?? '-' }}</template></el-table-column><el-table-column label="缺失率"><template #default="{row}">{{ pct(row.rate) }}</template></el-table-column></el-table></div></el-col>
      <el-col :xs="24" :lg="12"><div class="page-card"><h3 class="section-title">集中错误</h3><el-table :data="errorRows" border><template #empty><el-empty description="无错误数据" /></template><el-table-column prop="error_code" label="Error code" /><el-table-column prop="count" label="数量" width="100" /><el-table-column label="占比" width="110"><template #default="{row}">{{ pct(row.rate) }}</template></el-table-column></el-table></div></el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed, defineComponent, h, onMounted, reactive, ref } from 'vue'
import { ElEmpty, ElTable, ElTableColumn } from 'element-plus'
import dayjs from 'dayjs'
import http from '@/api/http'

const loading=ref(false), error=ref(''), data=ref({}), range=ref([])
const filters=reactive({platform:''})
const overall=computed(()=>data.value.overall||{})
const hasData=computed(()=>Number(overall.value.total_count||0)>0)
const cards=computed(()=>[
  {label:'总采集量',value:Number(overall.value.total_count||0)},
  {label:'PASS',value:Number(overall.value.accepted_count||0)},
  {label:'QUARANTINE',value:Number(overall.value.quarantine_count||0)},
  {label:'Quality pass rate',value:ratio(overall.value.quality_pass_rate),suffix:'%',precision:2},
  {label:'Parser failure rate',value:ratio(overall.value.parser_failure_rate),suffix:'%',precision:2},
  {label:'SKU 异常率',value:ratio(overall.value.sku_abnormal_rate),suffix:'%',precision:2},
])
const parserRows=computed(()=>data.value.by_parser_version||[]), rulesRows=computed(()=>data.value.by_quality_rules_version||[])
const missingRows=computed(()=>data.value.key_field_missing_rates||[{field:'price',count:overall.value.price_missing_count||0,total:overall.value.total_count||0,rate:overall.value.price_missing_rate||0}])
const errorRows=computed(()=>data.value.top_error_codes||(data.value.top_failure_reasons||[]).map(x=>({error_code:x.failure_reason,count:x.occurrences,rate:overall.value.total_count?x.occurrences/overall.value.total_count:0})))
const anomalies=computed(()=>data.value.anomalies||data.value.alerts||[])
function anomalyText(a){
  if(typeof a==='string') return a
  if(a?.title||a?.message) return a.title||a.message
  if(a?.type==='quarantine_rate_high') return `Quarantine rate 过高：${pct(a.rate)}`
  if(a?.type==='parser_failure_rate_high') return `Parser failure rate 过高：${pct(a.rate)}`
  if(a?.type==='parser_version_degraded') return `Parser ${a.version||'-'} 质量显著下降：通过率 ${pct(a.rate)}`
  if(a?.type==='failure_reason_concentrated') return `失败原因集中：${a.failure_reason||'-'}（${a.occurrences||0} 次）`
  return a?.type||'检测到质量异常'
}
function ratio(v){const n=Number(v||0);return n<=1?n*100:n} function pct(v){return `${ratio(v).toFixed(2)}%`}
const MetricTable=defineComponent({props:{rows:Array,label:String},setup(props){return()=>h(ElTable,{data:props.rows||[],border:true},{empty:()=>h(ElEmpty,{description:'无版本分组数据'}),default:()=>[h(ElTableColumn,{prop:'version',label:props.label,minWidth:150}),h(ElTableColumn,{prop:'total_count',label:'总量',width:90}),h(ElTableColumn,{prop:'accepted_count',label:'PASS',width:90}),h(ElTableColumn,{prop:'quarantine_count',label:'隔离',width:90}),h(ElTableColumn,{label:'通过率',width:110},{default:({row})=>pct(row.quality_pass_rate)})]})}})
async function load(){loading.value=true;error.value='';try{const params={};Object.entries(filters).forEach(([k,v])=>{if(v)params[k]=v});if(range.value?.length){params.start_at=dayjs(range.value[0]).toISOString();params.end_at=dayjs(range.value[1]).toISOString()}const res=await http.get('/api/management/quality/metrics',{params});data.value=res.data||{}}catch(e){data.value={};error.value=e.response?.data?.detail||e.message||'加载质量指标失败'}finally{loading.value=false}}
onMounted(load)
</script>
<style scoped>.metrics{row-gap:12px}.anomaly{margin-top:12px}</style>
