import { createRouter, createWebHistory } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { hasRoutePermissions } from './permissions.js'

const routes = [
  { path: '/login', name: 'login', component: () => import('@/views/Login.vue'), meta: { public: true } },
  {
    path: '/',
    component: () => import('@/layout/AdminLayout.vue'),
    redirect: '/devices',
    children: [
      { path: 'devices', name: 'devices', component: () => import('@/views/devices/DeviceList.vue'), meta: { title: '设备管理', perm: 'device:view' } },
      { path: 'devices/:id/live', name: 'device-live', component: () => import('@/views/devices/DeviceLive.vue'), meta: { title: '实时监控', perm: 'device:view' } },
      { path: 'devices/:id/cast', name: 'device-cast', component: () => import('@/views/devices/DeviceCast.vue'), meta: { title: '实时投屏', perm: 'device:cast' } },
      { path: 'tasks', name: 'tasks', component: () => import('@/views/tasks/TaskList.vue'), meta: { title: '任务调度', perm: 'task:view' } },
      { path: 'tasks/create', name: 'task-create', component: () => import('@/views/tasks/TaskCreate.vue'), meta: { title: '创建任务', perm: 'task:create' } },
      { path: 'tasks/:id', name: 'task-detail', component: () => import('@/views/tasks/TaskDetail.vue'), meta: { title: '任务详情', perm: 'task:view' } },
      { path: 'tasks/:id/trace', name: 'task-trace', component: () => import('@/views/management/TaskTrace.vue'), meta: { title: '执行轨迹', perm: 'task:view' } },
      { path: 'tasks/:taskId/results/:resourceKind/:resourceId', name: 'task-result-evidence', component: () => import('@/views/management/TaskResultEvidence.vue'), meta: { title: '采集证据', perms: ['task:view', 'data:view'] } },
      { path: 'products', name: 'products', component: () => import('@/views/data/ProductList.vue'), meta: { title: '商品资料库', perm: 'data:view' } },
      { path: 'products/excel-match', name: 'product-excel-match', component: () => import('@/views/excel/ExcelMatch.vue'), props: { mode: 'library-match' }, meta: { title: 'Excel批量查库/导出', perms: ['data:view', 'excel:match'] } },
      { path: 'products/:id/timeline', name: 'product-timeline', component: () => import('@/views/management/ProductTimeline.vue'), meta: { title: '商品快照时间线', perm: 'data:view' } },
      { path: 'quality', name: 'quality', component: () => import('@/views/management/QualityDashboard.vue'), meta: { title: '数据质量', perm: 'data:view' } },
      { path: 'quarantines', name: 'quarantines', component: () => import('@/views/management/QuarantineList.vue'), meta: { title: 'Quarantine 工作台', perm: 'data:view' } },
      { path: 'excel', name: 'excel', redirect: { name: 'task-create', query: { source: 'excel' } }, meta: { title: '创建采集任务', perm: 'task:create' } },
      { path: 'accounts', name: 'accounts', component: () => import('@/views/accounts/AccountList.vue'), meta: { title: '账号养护', perm: 'account:view' } },
      { path: 'reports', name: 'reports', component: () => import('@/views/reports/ReportOverview.vue'), meta: { title: '报表分析', perm: 'report:view' } },
      { path: 'users', name: 'users', component: () => import('@/views/system/Users.vue'), meta: { title: '人员管理', perm: 'user:manage' } },
      { path: 'roles', name: 'roles', component: () => import('@/views/system/Roles.vue'), meta: { title: '角色权限', perm: 'role:manage' } },
      { path: 'logs', name: 'logs', component: () => import('@/views/system/OpLogs.vue'), meta: { title: '操作日志', perm: 'log:view' } },
      { path: 'settings', name: 'settings', component: () => import('@/views/system/Settings.vue'), meta: { title: '系统设置', perm: 'system:config' } },
      { path: 'profile', name: 'profile', component: () => import('@/views/profile/Profile.vue'), meta: { title: '个人中心' } },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to) => {
  if (to.meta.public) return true
  const store = useUserStore()
  if (!store.token) return '/login'
  if (!store.profile) {
    try {
      await store.fetchMe()
    } catch {
      store.logout()
      return '/login'
    }
  }
  if (!hasRoutePermissions(to.meta, (permission) => store.hasPerm(permission))) {
    return '/profile'
  }
  return true
})

export default router
