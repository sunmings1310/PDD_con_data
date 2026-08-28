import assert from 'node:assert/strict'
import {
  buildCanonicalPayload,
  chooseCandidate,
  normalizeExcelRows,
  normalizeManualRows,
  prepareDraftRows,
  reviewDraft,
  stableDedupKey,
} from '../src/utils/taskDraft.js'

const config = { max_detail: 10, delay_min_sec: 2, busy_response: 'retry' }
const task = { task_name: '统一导入', task_type: 'collect', platform_code: 'pinduoduo', device_id: null, priority: 5, config }

const manual = prepareDraftRows(normalizeManualRows(' 感冒灵\n感冒灵\nhttps://mobile.yangkeduo.com/goods.html?goods_id=123 ', 'pinduoduo'), 'pinduoduo')
assert.equal(manual[0].dispatch_status, 'ready')
assert.equal(manual[1].error_codes.at(-1), 'DUPLICATE_DRAFT_INPUT')
assert.equal(manual[1].selection_status, 'excluded')
assert.equal(stableDedupKey('pinduoduo', manual[2]), 'pinduoduo|product|123')
assert.deepEqual(reviewDraft(manual), { total: 3, ready: 2, invalid: 0, duplicate: 1, excluded: 1, choice_required: 0, blocked: 1 })
console.log('MANUAL_ROW_STATES=PASS duplicate=excluded platform_product_id=123')

let excel = prepareDraftRows(normalizeExcelRows([
  { row_index: 4, match_status: 'unique', input_approval_no: 'H1', input_product_name: '药A', input_spec: '10mg', input_manufacturer: '厂A', search_keyword: '药A' },
  { row_index: 5, match_status: 'multiple', input_approval_no: 'H2', input_product_name: '药B', input_spec: '20mg', input_manufacturer: '厂B', candidates: [{ goods_id: 'b-1' }] },
  { row_index: 6, match_status: 'unmatched', input_approval_no: 'H3', input_product_name: '药C', input_spec: '30mg', input_manufacturer: '厂C' },
  { row_index: 7, match_status: 'unmatched', input_approval_no: '', input_product_name: '药D', input_spec: '40mg', input_manufacturer: '厂D' },
], 'pinduoduo'), 'pinduoduo')
assert.equal(excel[0].match_status, 'matched')
assert.equal(excel[1].selection_status, 'choice_required')
assert.equal(excel[1].dispatch_status, 'blocked')
assert.equal(excel[2].dispatch_status, 'ready')
assert.equal(excel[3].validation_status, 'invalid')
assert.throws(() => buildCanonicalPayload({ submissionId: 'same-id', source: 'excel', task, rows: excel }), /TASK_DRAFT_NOT_SUBMITTABLE/)
excel = chooseCandidate(excel, 'excel:5', { goods_id: 'b-1' }).filter((row) => row.row_id !== 'excel:7')
const excelPayload = buildCanonicalPayload({ submissionId: 'same-id', source: 'excel', task, rows: excel })
assert.equal(excelPayload.targets.length, 3)
assert.equal(excelPayload.targets[1].platform_product_id, 'b-1')
assert.deepEqual(Object.keys(excelPayload), ['submission_id', 'source', 'task_name', 'task_type', 'platform_code', 'device_id', 'priority', 'config', 'targets'])
console.log('EXCEL_ROW_STATES=PASS matched=true multiple=choice_required unmatched=ready invalid=blocked')
console.log('CANONICAL_PAYLOAD=PASS source=excel targets=3 submission_id=reusable')
