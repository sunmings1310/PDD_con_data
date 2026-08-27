import assert from 'node:assert/strict'
import { createRequestGeneration } from '../src/utils/requestGeneration.js'

const guard = createRequestGeneration()
const state = { task: null, results: [], logs: [], selection: [1], editOpen: true }
const reset = () => Object.assign(state, {
  task: null, results: [], logs: [], selection: [], editOpen: false,
})

const deferred = () => {
  let resolve
  const promise = new Promise((done) => { resolve = done })
  return { promise, resolve }
}
const a = deferred()
const b = deferred()
const tokenA = guard.reset('A', reset)
const write = async (request, token, scope) => {
  const value = await request.promise
  if (guard.isCurrent(token, scope)) state.task = value
}
const writeA = write(a, tokenA, 'A')
state.selection = [99]
state.editOpen = true
const tokenB = guard.reset('B', reset)
assert.deepEqual(state, { task: null, results: [], logs: [], selection: [], editOpen: false })
const writeB = write(b, tokenB, 'B')
b.resolve({ task_id: 'B' })
await writeB
a.resolve({ task_id: 'A' })
await writeA
assert.deepEqual(state.task, { task_id: 'B' })
assert.equal(guard.isCurrent(tokenA, 'A'), false)
assert.equal(guard.isCurrent(tokenB, 'B'), true)
console.log('STALE_RACE=PASS winner=B stale_A_ignored=true reset=task/results/logs/selection/edit')
