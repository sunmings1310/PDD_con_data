<template>
  <div class="page-card">
    <h2 class="page-title">个人中心</h2>
    <el-descriptions :column="2" border>
      <el-descriptions-item label="账号">{{ store.profile?.username }}</el-descriptions-item>
      <el-descriptions-item label="姓名">{{ store.profile?.real_name }}</el-descriptions-item>
      <el-descriptions-item label="角色">{{ store.profile?.role_name }}</el-descriptions-item>
      <el-descriptions-item label="权限数">{{ (store.profile?.perms || []).length }}</el-descriptions-item>
    </el-descriptions>

    <h3 class="section-title" style="margin-top:20px">修改密码</h3>
    <el-form label-width="100px" style="max-width:480px">
      <el-form-item label="原密码"><el-input v-model="pwd.old_password" type="password" show-password /></el-form-item>
      <el-form-item label="新密码"><el-input v-model="pwd.new_password" type="password" show-password /></el-form-item>
      <el-form-item><el-button type="primary" @click="changePwd">保存密码</el-button></el-form-item>
    </el-form>

    <h3 class="section-title">我的操作日志</h3>
    <el-table :data="logs" border stripe>
      <el-table-column prop="action_code" label="动作" width="140" />
      <el-table-column prop="detail_text" label="详情" />
      <el-table-column label="时间" width="170">
        <template #default="{ row }">{{ fmt(row.create_time) }}</template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import dayjs from 'dayjs'
import { ElMessage } from 'element-plus'
import http from '@/api/http'
import { useUserStore } from '@/stores/user'

const store = useUserStore()
const logs = ref([])
const pwd = reactive({ old_password: '', new_password: '' })
function fmt(v) { return v ? dayjs(v).format('YYYY-MM-DD HH:mm:ss') : '-' }

async function changePwd() {
  await http.post('/api/auth/change-password', pwd)
  ElMessage.success('密码已修改')
  pwd.old_password = ''
  pwd.new_password = ''
}

onMounted(async () => {
  const res = await http.get('/api/auth/my-logs')
  logs.value = res.data || []
})
</script>
