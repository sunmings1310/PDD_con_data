import assert from 'node:assert/strict'
import {
  createRequestGeneration, REQUEST_FAILED, REQUEST_STALE, runGuardedAfter,
} from '../src/utils/requestGeneration.js'

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

const confirmGuard = createRequestGeneration()
const confirmA = deferred()
const confirmTokenA = confirmGuard.reset('A')
let postedTask = null
const guardedPost = runGuardedAfter(
  confirmA.promise, confirmGuard, confirmTokenA, 'A', async () => { postedTask = 'A' },
)
confirmGuard.reset('B')
confirmA.resolve(true)
const confirmResult = await guardedPost
assert.equal(confirmResult.status, REQUEST_STALE)
assert.equal(postedTask, null)
console.log('REQUEUE_CONFIRM_RACE=PASS captured_task=A current_task=B stale_request_sent=false')

const traceGuard = createRequestGeneration()
const traceA = deferred()
const traceState = { selectedJob: { job_id: 'B-job' }, selectedAttempt: { attempt_id: 'B-attempt' }, attempts: ['B-attempt'], events: ['B-event'] }
const tokenTraceA = traceGuard.reset('A')
const fetchTraceA = async () => {
  await traceA.promise
  return traceGuard.isCurrent(tokenTraceA, 'A') ? REQUEST_FAILED : REQUEST_STALE
}
const loadJobsA = async () => {
  const outcome = await fetchTraceA()
  if (outcome === REQUEST_FAILED) Object.assign(traceState, { selectedJob: null, selectedAttempt: null, attempts: [], events: [] })
}
const oldLoad = loadJobsA()
traceGuard.reset('B')
traceA.resolve(new Error('late A failure'))
await oldLoad
assert.deepEqual(traceState, { selectedJob: { job_id: 'B-job' }, selectedAttempt: { attempt_id: 'B-attempt' }, attempts: ['B-attempt'], events: ['B-event'] })
console.log('TASK_TRACE_RACE=PASS stale_A_outcome=stale B_selection_attempts_events_preserved=true')
