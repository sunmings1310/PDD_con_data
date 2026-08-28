#!/usr/bin/env node
const { execFileSync } = require('node:child_process')
const { createHash } = require('node:crypto')
const { mkdirSync, readFileSync, rmSync, writeFileSync } = require('node:fs')
const { dirname, resolve, relative } = require('node:path')
const target = process.argv[2]
if (!target) throw new Error('usage: ROLLBACK.sh <target-copy-root>')
const root = execFileSync('git', ['rev-parse', '--show-toplevel'], { encoding: 'utf8' }).trim()
const targetRoot = resolve(target)
if (relative(root, targetRoot).startsWith('..')) throw new Error('ROLLBACK_REFUSED: target must stay under repository root')
const base = '807cfb4eff9c3830f9a7f3ad4f62f1f07d183b41'
const files = ['web/scripts/test-task-import-components.mjs','web/src/utils/requestGeneration.js','web/src/views/data/ProductList.vue','web/src/views/management/QualityDashboard.vue','web/src/views/management/QuarantineList.vue','web/src/views/tasks/TaskCreate.vue','web/src/views/tasks/TaskDetail.vue','web/src/views/tasks/TaskList.vue']
for (const file of files) { const content=execFileSync('git',['show',`${base}:${file}`]); const output=resolve(targetRoot,file); mkdirSync(dirname(output),{recursive:true});writeFileSync(output,content);const expected=createHash('sha256').update(content).digest('hex');const actual=createHash('sha256').update(readFileSync(output)).digest('hex');if(actual!==expected)throw new Error(`ROLLBACK_HASH_MISMATCH=${file}`);console.log(`RESTORED_FILE=${file} RESTORED_SHA256=${actual}`) }
rmSync(resolve(targetRoot,'web/src/utils/taskStatus.js'),{force:true})
console.log('REMOVED_NEW_FILE=web/src/utils/taskStatus.js')
console.log('ROLLBACK_RESULT=web_state_ux_sources_restored')
console.log('ROLLBACK_EXIT=0')
console.log('ROLLBACK_MATCH=yes')
