export function selectedTenantContext(contexts, enterpriseId, workspaceId) {
  return (contexts || []).find(
    (context) => String(context.enterprise_id) === String(enterpriseId || '')
      && String(context.workspace_id) === String(workspaceId || ''),
  ) || null
}

export function permissionsForTenant(contexts, enterpriseId, workspaceId) {
  const context = selectedTenantContext(contexts, enterpriseId, workspaceId)
  if (!context || !Array.isArray(context.perms)) return []
  return [...new Set(context.perms.filter((permission) => typeof permission === 'string' && permission))]
}
