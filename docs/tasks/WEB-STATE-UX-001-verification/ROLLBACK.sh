#!/usr/bin/env node
const { execFileSync } = require('node:child_process')
const { createHash } = require('node:crypto')
const { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } = require('node:fs')
const { dirname, resolve, relative } = require('node:path')
const target = process.argv[2]
if (!target) throw new Error('usage: ROLLBACK.sh <target-copy-root>')
const root = execFileSync('git', ['rev-parse', '--show-toplevel'], { encoding: 'utf8' }).trim()
const targetRoot = resolve(target)
if (!existsSync(targetRoot) || relative(root, targetRoot).startsWith('..')) { console.error('BLOCKED=target_missing_or_outside_root'); process.exit(2) }
const base = '807cfb4eff9c3830f9a7f3ad4f62f1f07d183b41'
const files = ['web/scripts/test-task-import-components.mjs','web/src/utils/requestGeneration.js','web/src/utils/taskStatus.js','web/src/views/data/ProductList.vue','web/src/views/management/QualityDashboard.vue','web/src/views/management/QuarantineList.vue','web/src/views/tasks/TaskCreate.vue','web/src/views/tasks/TaskDetail.vue','web/src/views/tasks/TaskList.vue']
const sha = (bytes) => createHash('sha256').update(bytes).digest('hex')
const manifest = readFileSync(resolve(root, 'docs/tasks/WEB-STATE-UX-001-verification/MODIFIED_FILE'), 'utf8')
const expected = new Map([...manifest.matchAll(/^MODIFIED_SHA256=(\S+)\s+([0-9a-f]{64})$/gm)].map(([, file, hash]) => [file, hash]))
for (const file of files) {
  const output = resolve(targetRoot, file)
  const actual = existsSync(output) ? sha(readFileSync(output)) : 'MISSING'
  const wanted = expected.get(file)
  console.log(`BEFORE_FILE=${file} BEFORE_SHA256=${actual} EXPECTED_MODIFIED_SHA256=${wanted || 'MISSING'}`)
  if (!wanted || actual !== wanted) { console.error(`BLOCKED=target_not_changed:${file}`); process.exit(2) }
}
for (const file of files.filter((file) => file !== 'web/src/utils/taskStatus.js')) {
  const content = execFileSync('git', ['show', `${base}:${file}`])
  const output = resolve(targetRoot, file); mkdirSync(dirname(output), { recursive: true }); writeFileSync(output, content)
  const restored = sha(readFileSync(output)); const baseHash = sha(content)
  console.log(`RESTORED_FILE=${file} RESTORED_SHA256=${restored} BASE_SHA256=${baseHash}`)
  if (restored !== baseHash) throw new Error(`ROLLBACK_HASH_MISMATCH=${file}`)
}
rmSync(resolve(targetRoot, 'web/src/utils/taskStatus.js'), { force: true })
console.log('REMOVED_NEW_FILE=web/src/utils/taskStatus.js')
console.log('ROLLBACK_RESULT=web_state_ux_sources_restored')
console.log('ROLLBACK_EXIT=0')
console.log('ROLLBACK_MATCH=yes')
