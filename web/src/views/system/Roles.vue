<template>
  <div class="page-card">
    <div class="toolbar">
      <el-button type="primary" @click="openEdit()">新建角色</el-button>
      <el-button @click="load">刷新</el-button>
    </div>
    <el-table :data="list" border stripe>
      <el-table-column prop="role_code" label="编码" width="160" />
      <el-table-column prop="role_name" label="名称" width="160" />
      <el-table-column prop="remark" label="备注" />
      <el-table-column label="权限数" width="100">
        <template #default="{ row }">{{ (row.perms || []).length }}</template>
      </el-table-column>
      <el-table-column label="操作" width="120">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEdit(row)">编辑权限</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="visible" :title="form.role_id ? '编辑角色' : '新建角色'" width="640px">
      <el-form label-width="90px">
        <el-form-item label="编码"><el-input v-model="form.role_code" :disabled="!!form.role_id" /></el-form-item>
        <el-form-item label="名称"><el-input v-model="form.role_name" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="form.remark" /></el-form-item>
        <el-form-item label="权限">
          <el-checkbox-group v-model="form.perms">
            <el-checkbox v-for="p in catalog" :key="p.code" :label="p.code" :value="p.code">{{ p.name }}</el-checkbox>
          </el-checkbox-group>
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
import { ElMessage } from 'element-plus'
import http from '@/api/http'

const list = ref([])
const catalog = ref([])
const visible = ref(false)
const form = reactive({ role_id: null, role_code: '', role_name: '', remark: '', perms: [] })

async function load() {
  const [r, c] = await Promise.all([http.get('/api/roles'), http.get('/api/perms/catalog')])
  list.value = r.data || []
  catalog.value = c.data || []
}

function openEdit(row) {
  Object.assign(form, {
    role_id: row?.role_id || null,
    role_code: row?.role_code || '',
    role_name: row?.role_name || '',
    remark: row?.remark || '',
    perms: [...(row?.perms || [])],
  })
  visible.value = true
}

async function save() {
  if (form.role_id) {
    await http.put(`/api/roles/${form.role_id}`, form)
  } else {
    await http.post('/api/roles', form)
  }
  ElMessage.success('已保存')
  visible.value = false
  load()
}

onMounted(load)
</script>
