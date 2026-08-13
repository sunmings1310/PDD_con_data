<template>
  <div class="page-card">
    <div class="toolbar">
      <el-input v-model="username" placeholder="账号" clearable style="width:160px" />
      <el-button type="primary" @click="load">查询</el-button>
      <span style="color:#86909C;font-size:12px">操作日志永久留存，不可删除</span>
    </div>
    <el-table :data="list" border stripe>
      <el-table-column prop="log_id" label="ID" width="90" />
      <el-table-column prop="username" label="账号" width="120" />
      <el-table-column prop="module_code" label="模块" width="100" />
      <el-table-column prop="action_code" label="动作" width="140" />
      <el-table-column prop="detail_text" label="详情" min-width="220" show-overflow-tooltip />
      <el-table-column prop="ip_addr" label="IP" width="130" />
      <el-table-column label="时间" width="170">
        <template #default="{ row }">{{ fmt(row.create_time) }}</template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import dayjs from 'dayjs'
import http from '@/api/http'

const list = ref([])
const username = ref('')
function fmt(v) { return v ? dayjs(v).format('YYYY-MM-DD HH:mm:ss') : '-' }
async function load() {
  const q = username.value ? `?username=${encodeURIComponent(username.value)}` : ''
  const res = await http.get(`/api/op-logs${q}`)
  list.value = res.data || []
}
onMounted(load)
</script>
