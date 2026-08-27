export function requiredRoutePermissions(meta = {}) {
  if (Array.isArray(meta.perms)) return meta.perms.filter(Boolean)
  return meta.perm ? [meta.perm] : []
}

export function hasRoutePermissions(meta, hasPermission) {
  return requiredRoutePermissions(meta).every((permission) => hasPermission(permission))
}
