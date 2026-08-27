const STORAGE_KEYS = Object.freeze({
  token: 'sjzq_token',
  enterpriseId: 'sjzq_enterprise_id',
  workspaceId: 'sjzq_workspace_id',
})

function browserStorage() {
  return typeof globalThis.localStorage === 'undefined' ? null : globalThis.localStorage
}

function read(storage, key) {
  return storage?.getItem(key) || ''
}

function normalizedContext(value = {}, generation = 0) {
  return Object.freeze({
    token: String(value.token || ''),
    enterpriseId: String(value.enterpriseId || ''),
    workspaceId: String(value.workspaceId || ''),
    generation,
  })
}

function contextsEqual(left, right) {
  return left.token === right.token
    && left.enterpriseId === right.enterpriseId
    && left.workspaceId === right.workspaceId
}

function persist(storage, context) {
  if (!storage) return
  for (const [field, key] of Object.entries(STORAGE_KEYS)) {
    if (context[field]) storage.setItem(key, context[field])
    else storage.removeItem(key)
  }
}

export function headersForContext(snapshot) {
  const headers = {}
  if (snapshot.token) headers.Authorization = `Bearer ${snapshot.token}`
  if (snapshot.enterpriseId) headers['X-Enterprise-Id'] = snapshot.enterpriseId
  if (snapshot.workspaceId) headers['X-Workspace-Id'] = snapshot.workspaceId
  return Object.freeze(headers)
}

export function createClientContextProvider({ storage = browserStorage() } = {}) {
  let context = normalizedContext({
    token: read(storage, STORAGE_KEYS.token),
    enterpriseId: read(storage, STORAGE_KEYS.enterpriseId),
    workspaceId: read(storage, STORAGE_KEYS.workspaceId),
  })
  let requestSequence = 0
  const activeRequests = new Map()

  const abortActive = () => {
    for (const controller of activeRequests.values()) controller.abort('client-context-changed')
    activeRequests.clear()
  }

  const update = (changes, options = {}) => {
    const next = normalizedContext({ ...context, ...changes }, context.generation)
    if (!contextsEqual(context, next) || options.forceGeneration) {
      abortActive()
      context = normalizedContext(next, context.generation + 1)
    }
    if (options.persist !== false) persist(storage, context)
    return context
  }

  return Object.freeze({
    getSnapshot() {
      return context
    },
    update,
    clear() {
      return update({ token: '', enterpriseId: '', workspaceId: '' }, { forceGeneration: true })
    },
    beginRequest() {
      const snapshot = context
      const controller = new AbortController()
      const requestId = ++requestSequence
      activeRequests.set(requestId, controller)
      return Object.freeze({
        requestId,
        snapshot,
        signal: controller.signal,
        isCurrent: () => context.generation === snapshot.generation && !controller.signal.aborted,
        release: () => activeRequests.delete(requestId),
      })
    },
    activeCount: () => activeRequests.size,
  })
}

export function createSessionLifecycle(provider) {
  let resetState = () => {}
  let redirectToLogin = () => {}
  let invalidated = false

  return Object.freeze({
    bindReset(callback) {
      resetState = callback || (() => {})
    },
    bindRedirect(callback) {
      redirectToLogin = callback || (() => {})
    },
    activate(context) {
      invalidated = false
      return provider.update(context)
    },
    invalidate() {
      if (invalidated) return false
      invalidated = true
      provider.clear()
      resetState()
      redirectToLogin()
      return true
    },
    clear() {
      invalidated = true
      provider.clear()
      resetState()
    },
  })
}

export const clientContext = createClientContextProvider()
export const sessionLifecycle = createSessionLifecycle(clientContext)

export const getClientContext = () => clientContext.getSnapshot()
export const updateClientContext = (changes) => clientContext.update(changes)
export const activateClientSession = (context) => sessionLifecycle.activate(context)
export const clearClientSession = () => sessionLifecycle.clear()
export const invalidateClientSession = () => sessionLifecycle.invalidate()
export const bindSessionReset = (callback) => sessionLifecycle.bindReset(callback)
export const bindUnauthorizedRedirect = (callback) => sessionLifecycle.bindRedirect(callback)
