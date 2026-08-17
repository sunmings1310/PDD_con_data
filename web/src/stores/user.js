import { defineStore } from 'pinia'
import http from '@/api/http'

export const useUserStore = defineStore('user', {
  state: () => ({
    token: localStorage.getItem('sjzq_token') || '',
    profile: null,
    tenantContexts: [],
    enterpriseId: localStorage.getItem('sjzq_enterprise_id') || '',
    workspaceId: localStorage.getItem('sjzq_workspace_id') || '',
    summary: {
      online_devices: 0,
      running_tasks: 0,
      pending_tasks: 0,
      product_count: 0,
    },
  }),
  getters: {
    perms: (s) => s.profile?.perms || [],
    isLogin: (s) => !!s.token,
  },
  actions: {
    hasPerm(code) {
      if (!code) return true
      if (this.profile?.role_code === 'super_admin') return true
      return this.perms.includes(code)
    },
    async login(username, password) {
      const res = await http.post('/api/auth/login', { username, password })
      this.token = res.data.token
      this.profile = res.data.user
      this.tenantContexts = this.profile.tenant_contexts || []
      if (!this.tenantContexts.some(x => String(x.enterprise_id) === this.enterpriseId && String(x.workspace_id) === this.workspaceId)) {
        const first = this.tenantContexts[0]
        if (first) this.selectTenant(first.enterprise_id, first.workspace_id)
      }
      localStorage.setItem('sjzq_token', this.token)
      await this.refreshSummary()
    },
    async fetchMe() {
      if (!this.token) return
      const res = await http.get('/api/auth/me')
      this.profile = res.data
      this.tenantContexts = this.profile.tenant_contexts || []
    },
    async refreshSummary() {
      if (!this.token || !this.enterpriseId || !this.workspaceId) return
      try {
        const res = await http.get('/api/dashboard/summary')
        this.summary = res.data
      } catch {
        /* ignore */
      }
    },
    logout() {
      this.token = ''
      this.profile = null
      localStorage.removeItem('sjzq_token')
      localStorage.removeItem('sjzq_enterprise_id')
      localStorage.removeItem('sjzq_workspace_id')
    },
    selectTenant(enterpriseId, workspaceId) {
      this.enterpriseId = String(enterpriseId)
      this.workspaceId = String(workspaceId)
      localStorage.setItem('sjzq_enterprise_id', this.enterpriseId)
      localStorage.setItem('sjzq_workspace_id', this.workspaceId)
    },
  },
})
