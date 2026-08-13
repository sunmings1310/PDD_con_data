<template>
  <div class="login-page">
    <div class="login-card page-card">
      <h1 class="page-title">多平台APP采集调度系统</h1>
      <p class="sub">Web 端调度 · APP 端执行</p>
      <el-form @submit.prevent="onSubmit" label-position="top">
        <el-form-item label="账号">
          <el-input v-model="form.username" placeholder="请输入账号" clearable />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" show-password placeholder="请输入密码" />
        </el-form-item>
        <el-button type="primary" style="width:100%" :loading="loading" native-type="submit">登录</el-button>
      </el-form>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'

const store = useUserStore()
const router = useRouter()
const loading = ref(false)
const form = reactive({ username: '', password: '' })

async function onSubmit() {
  loading.value = true
  try {
    await store.login(form.username, form.password)
    ElMessage.success('登录成功')
    router.replace('/devices')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background:
    radial-gradient(800px 320px at 20% 0%, #d6e8ff 0%, transparent 60%),
    linear-gradient(180deg, #eef3f9, #f5f7fa);
}
.login-card {
  width: 420px;
  padding: 28px 28px 18px;
}
.sub { margin: -8px 0 20px; color: var(--sjzq-gray); font-size: 12px; }
.tip { margin-top: 14px; color: var(--sjzq-gray); font-size: 12px; text-align: center; }
</style>
