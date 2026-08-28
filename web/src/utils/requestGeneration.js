export function createRequestGeneration() {
  let generation = 0
  let scope = ''

  const token = () => ({ generation, scope })
  return {
    reset(nextScope, resetState) {
      scope = String(nextScope)
      generation += 1
      resetState?.()
      return token()
    },
    next(nextScope = scope) {
      scope = String(nextScope)
      generation += 1
      return token()
    },
    capture() {
      return token()
    },
    isCurrent(candidate, currentScope = scope) {
      return Boolean(candidate)
        && candidate.generation === generation
        && candidate.scope === scope
        && candidate.scope === String(currentScope)
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
