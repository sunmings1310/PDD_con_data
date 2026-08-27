import { defineStore } from 'pinia'
import http from '@/api/http'
import {
  activateClientSession,
  clearClientSession,
  getClientContext,
  updateClientContext,
} from '@/api/clientContext'
import { permissionsForTenant, selectedTenantContext } from './tenantPermissions.js'

const emptySummary = () => ({
  online_devices: 0,
  running_tasks: 0,
  pending_tasks: 0,
  product_count: 0,
})

export const useUserStore = defineStore('user', {
  state: () => {
    const context = getClientContext()
    return {
      token: context.token,
      profile: null,
      tenantContexts: [],
      contextPermissions: [],
      enterpriseId: context.enterpriseId,
      workspaceId: context.workspaceId,
      contextGeneration: context.generation,
      summary: emptySummary(),
    }
  },
  getters: {
    perms: (s) => s.contextPermissions,
    isLogin: (s) => !!s.token,
  },
  actions: {
    hasPerm(code) {
      if (!code) return true
      return this.perms.includes(code)
    },
    async login(username, password) {
      const res = await http.post('/api/auth/login', { username, password })
      this.profile = res.data.user
      this.tenantContexts = this.profile.tenant_contexts || []
      const selected = this.tenantContexts.find(
        x => String(x.enterprise_id) === this.enterpriseId && String(x.workspace_id) === this.workspaceId,
      ) || this.tenantContexts[0]
      const context = activateClientSession({
        token: res.data.token,
        enterpriseId: selected?.enterprise_id || '',
        workspaceId: selected?.workspace_id || '',
      })
      this.token = context.token
      this.enterpriseId = context.enterpriseId
      this.workspaceId = context.workspaceId
      this.contextGeneration = context.generation
      this.contextPermissions = permissionsForTenant(
        this.tenantContexts, context.enterpriseId, context.workspaceId,
      )
      await this.refreshSummary()
    },
    async fetchMe() {
      if (!this.token) return
      const res = await http.get('/api/auth/me')
      this.profile = res.data
      this.tenantContexts = this.profile.tenant_contexts || []
      const selected = selectedTenantContext(
        this.tenantContexts, this.enterpriseId, this.workspaceId,
      ) || this.tenantContexts[0] || null
      if (selected) this.selectTenant(selected.enterprise_id, selected.workspace_id)
      else this.selectTenant('', '')
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
      clearClientSession()
    },
    resetSessionState() {
      const context = getClientContext()
      this.token = ''
      this.profile = null
      this.tenantContexts = []
      this.contextPermissions = []
      this.enterpriseId = ''
      this.workspaceId = ''
      this.contextGeneration = context.generation
      this.summary = emptySummary()
    },
    selectTenant(enterpriseId, workspaceId) {
      const context = updateClientContext({ enterpriseId, workspaceId })
      this.enterpriseId = context.enterpriseId
      this.workspaceId = context.workspaceId
      this.contextGeneration = context.generation
      this.contextPermissions = permissionsForTenant(
        this.tenantContexts, context.enterpriseId, context.workspaceId,
      )
      this.summary = emptySummary()
    },
  },
})
