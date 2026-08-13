<template>
  <div>
    <div class="page-card">
      <div class="toolbar">
        <el-button type="primary" v-if="store.hasPerm('account:manage')" @click="openCreate">新增养护账号</el-button>
        <el-button @click="load">刷新</el-button>
        <el-tag type="info">养护周期固定 5–7 天</el-tag>
      </div>
      <el-table :data="accounts" border stripe>
        <el-table-column prop="account_id" label="ID" width="75" />
        <el-table-column prop="platform_code" label="平台" width="100" />
        <el-table-column prop="account_name" label="账号" min-width="150" />
        <el-table-column prop="owner_username" label="运营" width="120" />
        <el-table-column prop="device_name" label="绑定设备" min-width="150" />
        <el-table-column prop="nurture_days" label="养护天数" width="100" />
        <el-table-column label="成熟时间" width="170"><template #default="{row}">{{ fmt(row.mature_at) }}</template></el-table-column>
        <el-table-column label="状态" width="110"><template #default="{row}"><el-tag :type="statusType(row.status)">{{ statusText(row.status) }}</el-tag></template></el-table-column>
        <el-table-column prop="block_reason" label="异常/封禁原因" min-width="180" />
        <el-table-column label="操作" width="210"><template #default="{row}">
          <el-button link type="primary" @click="edit(row)">编辑</el-button>
          <el-button link type="danger" @click="setStatus(row,'blocked')">封禁</el-button>
          <el-button link type="success" @click="setStatus(row,'ready')">恢复</el-button>
        </template></el-table-column>
      </el-table>
    </div>
    <div class="page-card" style="margin-top:16px">
      <h3>账号异常告警</h3>
      <el-table :data="alerts" border><el-table-column prop="level_code" label="级别" width="80" /><el-table-column prop="message" label="告警内容" /><el-table-column prop="status" label="状态" width="90" /><el-table-column label="操作" width="90"><template #default="{row}"><el-button v-if="row.status==='unread'" link type="primary" @click="ack(row)">确认</el-button></template></el-table-column></el-table>
    </div>
    <el-dialog v-model="visible" :title="form.account_id ? '编辑账号' : '新增养护账号'" width="560px">
      <el-form label-width="120px">
        <el-form-item label="平台"><el-select v-model="form.platform_code"><el-option label="拼多多" value="pinduoduo" /><el-option label="天猫" value="tmall" /></el-select></el-form-item>
        <el-form-item label="账号"><el-input v-model="form.account_name" /></el-form-item>
        <el-form-item label="绑定运营"><el-select v-model="form.owner_user_id"><el-option v-for="u in operators" :key="u.user_id" :label="u.real_name || u.username" :value="u.user_id" /></el-select></el-form-item>
        <el-form-item label="绑定设备"><el-select v-model="form.device_id" clearable><el-option v-for="d in devices" :key="d.device_id" :label="d.device_name || d.device_key" :value="d.device_id" /></el-select></el-form-item>
        <el-form-item label="养护天数"><el-radio-group v-model="form.nurture_days"><el-radio-button :value="5">5天</el-radio-button><el-radio-button :value="6">6天</el-radio-button><el-radio-button :value="7">7天</el-radio-button></el-radio-group></el-form-item>
        <el-form-item label="状态"><el-select v-model="form.status"><el-option v-for="s in statuses" :key="s" :label="statusText(s)" :value="s" /></el-select></el-form-item>
        <el-form-item label="异常原因"><el-input v-model="form.block_reason" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="visible=false">取消</el-button><el-button type="primary" @click="save">保存</el-button></template>
    </el-dialog>
  </div>
</template>
<script setup>
import { onMounted, reactive, ref } from 'vue'
import dayjs from 'dayjs'
import { ElMessage } from 'element-plus'
import http from '@/api/http'
import { useUserStore } from '@/stores/user'
const store=useUserStore(); const accounts=ref([]); const alerts=ref([]); const operators=ref([]); const devices=ref([]); const visible=ref(false)
const statuses=['nurturing','ready','blocked','abnormal','disabled']
const form=reactive({account_id:null,platform_code:'pinduoduo',account_name:'',owner_user_id:null,device_id:null,nurture_days:5,status:'nurturing',block_reason:''})
const fmt=v=>v?dayjs(v).format('YYYY-MM-DD HH:mm'):'-'
const statusText=v=>({nurturing:'养护中',ready:'可用',blocked:'已封禁',abnormal:'异常',disabled:'停用'})[v]||v
const statusType=v=>({ready:'success',nurturing:'warning',blocked:'danger',abnormal:'danger',disabled:'info'})[v]||'info'
async function load(){const [a,l,o,d]=await Promise.all([http.get('/api/accounts'),http.get('/api/accounts/alerts'),http.get('/api/accounts/operators'),http.get('/api/devices')]);accounts.value=a.data||[];alerts.value=l.data||[];operators.value=o.data||[];devices.value=d.data||[]}
function openCreate(){Object.assign(form,{account_id:null,platform_code:'pinduoduo',account_name:'',owner_user_id:operators.value[0]?.user_id||null,device_id:null,nurture_days:5,status:'nurturing',block_reason:''});visible.value=true}
function edit(row){Object.assign(form,{...row});visible.value=true}
async function save(){const res=form.account_id?await http.put(`/api/accounts/${form.account_id}`,form):await http.post('/api/accounts',form);if(!res.ok)return ElMessage.error(res.message||'保存失败');ElMessage.success('已保存');visible.value=false;load()}
async function setStatus(row,status){const reason=status==='blocked'?(prompt('请输入封禁原因')||'运营标记封禁'):'';const res=await http.put(`/api/accounts/${row.account_id}`,{status,block_reason:reason});if(!res.ok)return ElMessage.error(res.message);load()}
async function ack(row){await http.post(`/api/accounts/alerts/${row.alert_id}/ack`);load()}
onMounted(load)
</script>
