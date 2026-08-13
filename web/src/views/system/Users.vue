<template>
  <div class="page-card">
    <div class="toolbar">
      <el-input v-model="q.username" placeholder="账号" clearable style="width:160px" />
      <el-select v-model="q.role_id" clearable placeholder="角色" style="width:160px">
        <el-option v-for="r in roles" :key="r.role_id" :label="r.role_name" :value="r.role_id" />
      </el-select>
      <el-select v-model="q.status" clearable placeholder="状态" style="width:120px">
        <el-option label="启用" value="enabled" />
        <el-option label="禁用" value="disabled" />
      </el-select>
      <el-button @click="load">查询</el-button>
      <el-button type="primary" @click="openEdit()">新增用户</el-button>
    </div>
    <el-table :data="list" border stripe>
      <el-table-column prop="username" label="账号" width="140" />
      <el-table-column prop="real_name" label="姓名" width="120" />
      <el-table-column prop="mobile" label="手机号" width="140" />
      <el-table-column prop="role_name" label="角色" width="140" />
      <el-table-column prop="status" label="状态" width="100" />
      <el-table-column label="最后登录" width="170">
        <template #default="{ row }">{{ fmt(row.last_login_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="260">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button link @click="resetPwd(row)">重置密码</el-button>
          <el-button link type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="visible" :title="form.user_id ? '编辑用户' : '新增用户'" width="480px">
      <el-form label-width="90px">
        <el-form-item label="账号"><el-input v-model="form.username" :disabled="!!form.user_id" /></el-form-item>
        <el-form-item v-if="!form.user_id" label="初始密码">
          <el-input v-model="form.password" type="password" show-password placeholder="至少 12 个字符" />
        </el-form-item>
        <el-form-item label="姓名"><el-input v-model="form.real_name" /></el-form-item>
        <el-form-item label="手机号"><el-input v-model="form.mobile" /></el-form-item>
        <el-form-item label="角色">
          <el-select v-model="form.role_id" style="width:100%">
            <el-option v-for="r in roles" :key="r.role_id" :label="r.role_name" :value="r.role_id" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="form.status" style="width:100%">
            <el-option label="启用" value="enabled" />
            <el-option label="禁用" value="disabled" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="visible=false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import dayjs from 'dayjs'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/api/http'

const list = ref([])
const roles = ref([])
const visible = ref(false)
const q = reactive({ username: '', role_id: null, status: '' })
const form = reactive({ user_id: null, username: '', password: '', real_name: '', mobile: '', role_id: null, status: 'enabled' })

function fmt(v) { return v ? dayjs(v).format('YYYY-MM-DD HH:mm:ss') : '-' }

async function load() {
  const params = new URLSearchParams()
  if (q.username) params.set('username', q.username)
  if (q.role_id) params.set('role_id', q.role_id)
  if (q.status) params.set('status', q.status)
  const res = await http.get(`/api/users?${params}`)
  list.value = res.data || []
}

function openEdit(row) {
  Object.assign(form, {
    user_id: row?.user_id || null,
    username: row?.username || '',
    password: '',
    real_name: row?.real_name || '',
    mobile: row?.mobile || '',
    role_id: row?.role_id || roles.value[0]?.role_id,
    status: row?.status || 'enabled',
  })
  visible.value = true
}

async function save() {
  if (form.user_id) {
    await http.put(`/api/users/${form.user_id}`, form)
  } else {
    await http.post('/api/users', form)
  }
  ElMessage.success('已保存')
  visible.value = false
  load()
}

async function resetPwd(row) {
  const { value } = await ElMessageBox.prompt(
    `请为用户 ${row.username} 指定临时密码`,
    '重置密码',
    {
      inputType: 'password',
      inputPlaceholder: '至少 12 个字符',
      inputValidator: (v) => (v?.length >= 12 ? true : '临时密码至少 12 个字符'),
      confirmButtonText: '确认重置',
      cancelButtonText: '取消',
    },
  )
  await http.post(`/api/users/${row.user_id}/reset-password`, { password: value })
  ElMessage.success('密码已重置，请通过安全渠道交付临时密码')
}

async function remove(row) {
  await ElMessageBox.confirm(`确认删除用户 ${row.username}？`, '提示', { type: 'warning' })
  await http.delete(`/api/users/${row.user_id}`)
  ElMessage.success('已删除')
  load()
}

onMounted(async () => {
  const r = await http.get('/api/roles')
  roles.value = r.data || []
  load()
})
</script>
