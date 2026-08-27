export function createRequestGeneration() {
  let generation = 0
  let scope = ''

  return {
    reset(nextScope, resetState) {
      scope = String(nextScope)
      generation += 1
      resetState?.()
      return { generation, scope }
    },
    capture() {
      return { generation, scope }
    },
    isCurrent(token, currentScope = scope) {
      return Boolean(token)
        && token.generation === generation
        && token.scope === scope
        && token.scope === String(currentScope)
    },
  }
}

export const REQUEST_OK = 'ok'
export const REQUEST_FAILED = 'failed'
export const REQUEST_STALE = 'stale'

export async function runGuardedAfter(pending, guard, token, scope, action) {
  await pending
  if (!guard.isCurrent(token, scope)) return { status: REQUEST_STALE, value: undefined }
  return { status: REQUEST_OK, value: await action() }
}
