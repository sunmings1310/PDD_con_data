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
