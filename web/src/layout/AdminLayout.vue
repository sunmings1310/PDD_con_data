<template>
  <el-container class="layout">
    <el-aside width="220px" class="aside">
      <div class="brand">采集调度系统</div>
      <el-menu :default-active="route.path" router background-color="#001529" text-color="#ffffffa6" active-text-color="#fff">
        <el-menu-item v-if="store.hasPerm('device:view')" index="/devices">
          <el-icon><Monitor /></el-icon><span>设备管理</span>
        </el-menu-item>
        <el-menu-item v-if="store.hasPerm('task:view')" index="/tasks">
          <el-icon><List /></el-icon><span>任务调度</span>
        </el-menu-item>
        <el-menu-item v-if="store.hasPerm('data:view')" index="/products">
          <el-icon><Goods /></el-icon><span>商品资料库</span>
        </el-menu-item>
        <el-sub-menu v-if="store.hasPerm('data:view')" index="quality-management">
          <template #title>
            <el-icon><TrendCharts /></el-icon><span>质量与可观测性</span>
          </template>
          <el-menu-item index="/quality">数据质量</el-menu-item>
          <el-menu-item index="/quarantines">Quarantine 工作台</el-menu-item>
        </el-sub-menu>
        <el-menu-item v-if="store.hasPerm('excel:match')" index="/excel">
          <el-icon><Document /></el-icon><span>Excel匹配回填</span>
        </el-menu-item>
        <el-menu-item v-if="store.hasPerm('account:view')" index="/accounts">
          <el-icon><User /></el-icon><span>账号养护</span>
        </el-menu-item>
        <el-menu-item v-if="store.hasPerm('report:view')" index="/reports">
          <el-icon><TrendCharts /></el-icon><span>报表分析</span>
        </el-menu-item>
        <el-sub-menu v-if="store.hasPerm('user:manage') || store.hasPerm('role:manage') || store.hasPerm('system:config')" index="sys">
          <template #title>
            <el-icon><Setting /></el-icon><span>系统管理</span>
          </template>
          <el-menu-item v-if="store.hasPerm('user:manage')" index="/users">人员管理</el-menu-item>
          <el-menu-item v-if="store.hasPerm('role:manage')" index="/roles">角色权限</el-menu-item>
          <el-menu-item v-if="store.hasPerm('log:view')" index="/logs">操作日志</el-menu-item>
          <el-menu-item v-if="store.hasPerm('system:config')" index="/settings">系统设置</el-menu-item>
        </el-sub-menu>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="header">
        <div class="header-left">
          <span class="route-title">{{ route.meta.title || '工作台' }}</span>
        </div>
        <div class="header-right">
          <el-select :model-value="tenantKey" class="tenant-select" placeholder="选择企业 / Workspace" @change="onTenantChange">
            <el-option v-for="item in store.tenantContexts" :key="`${item.enterprise_id}:${item.workspace_id}`"
              :label="`${item.enterprise_name} / ${item.workspace_name}`"
              :value="`${item.enterprise_id}:${item.workspace_id}`" />
          </el-select>
          <el-tag type="success" effect="plain">在线设备 {{ store.summary.online_devices }}</el-tag>
          <el-tag type="warning" effect="plain">进行中任务 {{ store.summary.running_tasks }}</el-tag>
          <span class="clock">{{ nowText }}</span>
          <el-dropdown>
            <span class="user-entry">
              {{ store.profile?.real_name || store.profile?.username }}
              <small>（{{ store.profile?.role_name }}）</small>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="$router.push('/profile')">个人中心</el-dropdown-item>
                <el-dropdown-item divided @click="onLogout">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>
      <el-main class="main">
        <router-view :key="`${store.contextGeneration}:${route.fullPath}`" />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import dayjs from 'dayjs'
import { useUserStore } from '@/stores/user'
import { hasRoutePermissions } from '@/router/permissions'

const store = useUserStore()
const route = useRoute()
const router = useRouter()
const nowText = ref(dayjs().format('YYYY-MM-DD HH:mm:ss'))
const tenantKey = computed(() => `${store.enterpriseId}:${store.workspaceId}`)
let timer
let summaryTimer

onMounted(() => {
  store.refreshSummary()
  timer = setInterval(() => {
    nowText.value = dayjs().format('YYYY-MM-DD HH:mm:ss')
  }, 1000)
  summaryTimer = setInterval(() => store.refreshSummary(), 15000)
})

onUnmounted(() => {
  clearInterval(timer)
  clearInterval(summaryTimer)
})

function onLogout() {
  store.logout()
  router.replace('/login')
}
async function onTenantChange(value) {
  const [enterpriseId, workspaceId] = String(value).split(':')
  store.selectTenant(enterpriseId, workspaceId)
  if (!hasRoutePermissions(route.meta, (permission) => store.hasPerm(permission))) {
    await router.replace('/profile')
  }
  const [profileResult] = await Promise.allSettled([store.fetchMe()])
  if (profileResult.status === 'fulfilled'
      && !hasRoutePermissions(route.meta, (permission) => store.hasPerm(permission))) {
    await router.replace('/profile')
  }
  await store.refreshSummary()
}
</script>

<style scoped>
.layout { height: 100%; }
.aside {
  background: #001529;
  color: #fff;
}
.brand {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  font-weight: 700;
  color: #fff;
  border-bottom: 1px solid #ffffff1a;
}
.header {
  height: 56px;
  background: #fff;
  border-bottom: 1px solid var(--sjzq-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
}
.route-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--sjzq-title);
}
.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}
.tenant-select { width: 260px; }
.clock { color: var(--sjzq-gray); font-size: 12px; }
.user-entry {
  cursor: pointer;
  color: var(--sjzq-title);
}
.user-entry small { color: var(--sjzq-gray); }
.main { padding: 16px 20px 24px; }
.el-menu { border-right: none; }
</style>
