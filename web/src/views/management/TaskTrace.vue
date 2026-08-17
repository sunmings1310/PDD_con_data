<template>
  <div>
    <div class="page-card">
      <div class="toolbar"><el-button @click="$router.push(`/tasks/${route.params.id}`)">返回任务</el-button><el-button type="primary" @click="reload">刷新轨迹</el-button></div>
      <el-alert v-if="summaryError" :title="summaryError" type="error" show-icon :closable="false"><template #default><el-button link type="primary" @click="loadSummary">重试</el-button></template></el-alert>
      <div v-loading="summaryLoading"><el-empty v-if="!summaryLoading && !summaryError && !summary" description="任务轨迹摘要不存在" /><el-descriptions v-else-if="summary" :column="4" border><el-descriptions-item label="Task">#{{ task.task_id || route.params.id }} {{ task.task_name || '' }}</el-descriptions-item><el-descriptions-item label="状态"><el-tag>{{ task.status || '-' }}</el-tag></el-descriptions-item><el-descriptions-item label="Jobs">{{ jobCount }}</el-descriptions-item><el-descriptions-item label="Attempts">{{ summary.attempt_count ?? summary.counts?.attempts ?? '-' }}</el-descriptions-item><el-descriptions-item label="起止时间" :span="2">{{ fmt(task.create_time || task.started_at) }} → {{ fmt(task.end_time || task.finished_at) }}</el-descriptions-item><el-descriptions-item label="最终错误" :span="2"><el-text type="danger">{{ latestError }}</el-text></el-descriptions-item></el-descriptions></div>
    </div>

    <div class="page-card">
      <h3 class="section-title">Task 级事件</h3>
      <el-alert v-if="taskEvents.error" :title="taskEvents.error" type="error" show-icon :closable="false"><template #default><el-button link type="primary" @click="loadTaskEvents">重试</el-button></template></el-alert>
      <div v-loading="taskEvents.loading">
        <el-empty v-if="!taskEvents.loading && !taskEvents.items.length" description="该 Task 没有独立事件" />
        <el-timeline v-else><el-timeline-item v-for="event in taskEvents.items" :key="event.event_id" :timestamp="fmt(event.create_time || event.timestamp)" :type="event.error_code?'danger':'primary'" placement="top"><el-card shadow="never"><div class="event-title"><strong>{{ event.event_type || event.event }}</strong><span>{{ event.old_status || '-' }} → {{ event.new_status || '-' }}</span></div><el-space wrap><span v-if="event.job_id">Job #{{ event.job_id }}</span><span v-if="event.attempt_id">Attempt #{{ event.attempt_id }}</span><span>Device #{{ event.device_id || '-' }}</span><span>Trace {{ event.trace_id || '-' }}</span><el-text v-if="event.error_code" type="danger">{{ event.error_class || 'error' }} / {{ event.error_code }}</el-text></el-space><pre v-if="event.detail || event.detail_json">{{ pretty(event.detail || event.detail_json) }}</pre></el-card></el-timeline-item></el-timeline>
      </div>
      <pager :state="taskEvents" @page="v=>pageChange(taskEvents,v,loadTaskEvents)" @limit="v=>limitChange(taskEvents,v,loadTaskEvents)" />
    </div>

    <div class="page-card">
      <h3 class="section-title">Jobs</h3>
      <el-alert v-if="jobs.error" :title="jobs.error" type="error" show-icon :closable="false"><template #default><el-button link type="primary" @click="loadJobs">重试</el-button></template></el-alert>
      <el-table v-loading="jobs.loading" :data="jobs.items" border highlight-current-row @current-change="selectJob"><template #empty><el-empty :description="jobs.loading?'正在加载':'该 Task 没有 Job'" /></template><el-table-column prop="job_id" label="Job ID" width="100" /><el-table-column prop="job_key" label="Job key" min-width="220" show-overflow-tooltip /><el-table-column prop="status" label="状态" width="110"><template #default="{row}"><el-tag :type="statusType(row.status)">{{ row.status }}</el-tag></template></el-table-column><el-table-column prop="attempt_count" label="Attempts" width="100" /><el-table-column prop="device_id" label="Device" width="100" /><el-table-column label="业务结果" min-width="220"><template #default="{row}"><result-links :results="row.business_results" :job-id="row.job_id" /></template></el-table-column><el-table-column label="最近错误" min-width="210" show-overflow-tooltip><template #default="{row}">{{ [row.last_error_code,row.last_error_message].filter(Boolean).join(': ') || '-' }}</template></el-table-column><el-table-column label="更新时间" width="175"><template #default="{row}">{{ fmt(row.update_time) }}</template></el-table-column></el-table>
      <pager :state="jobs" @page="v=>pageChange(jobs,v,loadJobs)" @limit="v=>limitChange(jobs,v,loadJobs)" />
    </div>

    <div class="page-card">
      <h3 class="section-title">Attempts <small v-if="selectedJob">/ Job #{{ selectedJob.job_id }}</small></h3>
      <el-alert v-if="attempts.error" :title="attempts.error" type="error" show-icon :closable="false"><template #default><el-button link type="primary" @click="loadAttempts">重试</el-button></template></el-alert>
      <el-table v-loading="attempts.loading" :data="attempts.items" border highlight-current-row @current-change="selectAttempt"><template #empty><el-empty :description="selectedJob?(attempts.loading?'正在加载':'该 Job 没有 Attempt'):'请先选择 Job'" /></template><el-table-column prop="attempt_id" label="Attempt ID" width="115" /><el-table-column prop="attempt_no" label="#" width="60" /><el-table-column prop="status" label="状态" width="105"><template #default="{row}"><el-tag :type="statusType(row.status)">{{ row.status }}</el-tag></template></el-table-column><el-table-column prop="device_id" label="Device" width="90" /><el-table-column prop="worker_id" label="Worker" width="130" /><el-table-column prop="trace_id" label="Trace ID" min-width="180" show-overflow-tooltip /><el-table-column label="Lease" width="210"><template #default="{row}">{{ fmt(row.leased_at) }} → {{ fmt(row.lease_expires_at) }}</template></el-table-column><el-table-column label="业务结果" min-width="220"><template #default="{row}"><result-links :results="row.business_results" :job-id="row.job_id" /></template></el-table-column><el-table-column label="错误" min-width="190" show-overflow-tooltip><template #default="{row}">{{ [row.error_class,row.error_code,row.error_message].filter(Boolean).join(': ') || '-' }}</template></el-table-column></el-table>
      <pager :state="attempts" @page="v=>pageChange(attempts,v,loadAttempts)" @limit="v=>limitChange(attempts,v,loadAttempts)" />
    </div>

    <div class="page-card">
      <h3 class="section-title">事件时间线 <small v-if="selectedAttempt">/ Attempt #{{ selectedAttempt.attempt_id }}</small></h3>
      <el-alert v-if="events.error" :title="events.error" type="error" show-icon :closable="false"><template #default><el-button link type="primary" @click="loadEvents">重试</el-button></template></el-alert>
      <div v-loading="events.loading"><el-empty v-if="!selectedAttempt" description="请先选择 Attempt" /><el-empty v-else-if="!events.loading && !events.items.length" description="该 Attempt 没有事件" /><el-timeline v-else><el-timeline-item v-for="event in events.items" :key="event.event_id" :timestamp="fmt(event.create_time || event.timestamp)" :type="event.error_code?'danger':'primary'" placement="top"><el-card shadow="never"><div class="event-title"><strong>{{ event.event_type || event.event }}</strong><span>{{ event.old_status || '-' }} → {{ event.new_status || '-' }}</span></div><el-space wrap><span>Device #{{ event.device_id || selectedAttempt.device_id || '-' }}</span><span>Trace {{ event.trace_id || selectedAttempt.trace_id || '-' }}</span><el-text v-if="event.error_code" type="danger">{{ event.error_class || 'error' }} / {{ event.error_code }}</el-text></el-space><pre v-if="event.detail || event.detail_json">{{ pretty(event.detail || event.detail_json) }}</pre></el-card></el-timeline-item></el-timeline></div>
      <pager :state="events" @page="v=>pageChange(events,v,loadEvents)" @limit="v=>limitChange(events,v,loadEvents)" />
    </div>
  </div>
</template>

<script setup>
import { computed, defineComponent, h, onMounted, reactive, ref } from 'vue'
import { ElPagination } from 'element-plus'
import { RouterLink, useRoute } from 'vue-router'
import dayjs from 'dayjs'
import http from '@/api/http'

const route=useRoute(),summary=ref(null),summaryLoading=ref(false),summaryError=ref(''),selectedJob=ref(null),selectedAttempt=ref(null)
const task=computed(()=>summary.value?.task||summary.value||{})
const jobCount=computed(()=>summary.value?.job_count??Object.values(summary.value?.job_status_counts||{}).reduce((a,b)=>a+Number(b||0),0))
const latestError=computed(()=>task.value.error_msg||[summary.value?.latest_error?.error_class,summary.value?.latest_error?.error_code,summary.value?.latest_error?.error_message].filter(Boolean).join(': ')||'-')
function state(){return reactive({items:[],total:0,page:1,limit:20,loading:false,error:''})} const taskEvents=state(),jobs=state(),attempts=state(),events=state()
const Pager=defineComponent({props:{state:Object},emits:['page','limit'],setup(p,{emit}){return()=>p.state.total?h(ElPagination,{class:'pager',background:true,layout:'total, sizes, prev, pager, next',total:p.state.total,currentPage:p.state.page,pageSize:p.state.limit,pageSizes:[10,20,50],'onUpdate:currentPage':v=>emit('page',v),'onUpdate:pageSize':v=>emit('limit',v)}):null}})
const ResultLinks=defineComponent({props:{results:Array,jobId:[Number,String]},setup(p){return()=>{const rows=p.results||[];if(!rows.length)return h(RouterLink,{to:{path:'/quarantines',query:{job_id:p.jobId}}},{default:()=>'查看隔离记录'});return h('div',{class:'result-links'},rows.map((r,i)=>{if(r.quarantine_id)return h(RouterLink,{key:i,to:{path:'/quarantines',query:{job_id:p.jobId}}},{default:()=>`Quarantine #${r.quarantine_id}`});if(r.master_product_id)return h(RouterLink,{key:i,to:`/products/${r.master_product_id}/timeline`},{default:()=>`Snapshot #${r.snapshot_id||'-'}`});return h('span',{key:i},r.label||r.result_kind||r.type||r.result_type||'业务结果')}))}}})
function fmt(v){return v?dayjs(v).format('YYYY-MM-DD HH:mm:ss'):'-'} function statusType(v){return ['success','succeeded'].includes(v)?'success':['failed','dead','timeout','quarantined'].includes(v)?'danger':['running','leased','retry_wait'].includes(v)?'warning':'info'}
function pretty(v){if(typeof v==='string'){try{return JSON.stringify(JSON.parse(v),null,2)}catch{return v}}return JSON.stringify(v,null,2)}
async function fetchPage(s,url){s.loading=true;s.error='';try{const res=await http.get(url,{params:{page:s.page,limit:s.limit}});s.items=res.data?.items||[];s.total=Number(res.data?.total||0);s.page=Number(res.data?.page||s.page);s.limit=Number(res.data?.limit||s.limit)}catch(e){s.items=[];s.total=0;s.error=e.response?.data?.detail||e.message||'加载失败'}finally{s.loading=false}}
async function loadSummary(){summaryLoading.value=true;summaryError.value='';try{const res=await http.get(`/api/management/tasks/${route.params.id}/trace`);summary.value=res.data}catch(e){summary.value=null;summaryError.value=e.response?.data?.detail||e.message||'加载轨迹摘要失败'}finally{summaryLoading.value=false}}
function loadJobs(){return fetchPage(jobs,`/api/management/tasks/${route.params.id}/jobs`)} function loadAttempts(){return selectedJob.value?fetchPage(attempts,`/api/management/jobs/${selectedJob.value.job_id}/attempts`):Promise.resolve()} function loadEvents(){return selectedAttempt.value?fetchPage(events,`/api/management/attempts/${selectedAttempt.value.attempt_id}/events`):Promise.resolve()}
function loadTaskEvents(){return fetchPage(taskEvents,`/api/management/tasks/${route.params.id}/events`)}
function selectJob(row){selectedJob.value=row;selectedAttempt.value=null;attempts.page=1;attempts.items=[];events.items=[];if(row)loadAttempts()} function selectAttempt(row){selectedAttempt.value=row;events.page=1;events.items=[];if(row)loadEvents()}
function pageChange(s,v,fn){s.page=v;fn()} function limitChange(s,v,fn){s.limit=v;s.page=1;fn()} function reload(){loadSummary();loadTaskEvents();loadJobs();if(selectedJob.value)loadAttempts();if(selectedAttempt.value)loadEvents()}
onMounted(()=>{loadSummary();loadTaskEvents();loadJobs()})
</script>
<style scoped>.pager{margin-top:16px;justify-content:flex-end}.section-title small{font-weight:400;color:var(--sjzq-gray)}.event-title{display:flex;justify-content:space-between;margin-bottom:10px}.result-links{display:flex;flex-direction:column;gap:4px}pre{white-space:pre-wrap;word-break:break-word;background:#f7f8fa;padding:10px}</style>
