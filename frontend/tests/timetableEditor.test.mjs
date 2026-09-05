import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { compileScript, parse } from 'vue/compiler-sfc'
import { computed, nextTick, ref } from 'vue'
import { rangeErrors, rangesValid, sortedRanges } from '../src/components/timetableRanges.js'

test('inline editing preserves drafts across folding and grouping, cancels explicitly, and recovers from failed saves', async () => {
  const source = readFileSync(new URL('../src/views/TimetableImportView.vue', import.meta.url), 'utf8')
  const { descriptor } = parse(source)
  const script = compileScript(descriptor, { id: 'timetable-editor-test' }).content
    .replace(/^import .+$/gm, '').replace('export default', 'return')
  const period = { effective_from: '2026-09-01', effective_to: '2027-07-10' }
  const rows = [1, 2].map(id => ({ id, group_id: 1, ...period, effective_ranges: [{ ...period }],
    special_subjects: [], subjects: ['中文', '體育'], post_exam: id === 2, is_current: id === 1 }))
  let fail = false
  const requests = []
  const axios = {
    get: async url => ({ data: structuredClone(url === '/api/timetables' ? rows
      : url === '/api/timetable-groups' ? [{ id: 1, name: '2026–2027' }] : { active: true }) }),
    put: async (url, payload) => {
      if (fail) throw new Error('offline')
      requests.push({ url, payload })
      const row = rows.find(row => url.startsWith(`/api/timetables/${row.id}`))
      Object.assign(row, JSON.parse(JSON.stringify(payload)))
      if (payload.effective_from) row.effective_ranges = [{ effective_from: payload.effective_from, effective_to: payload.effective_to }]
      return { data: {} }
    },
  }
  const component = new Function('computed', 'nextTick', 'onBeforeUnmount', 'onMounted', 'ref', 'useI18n', 'axios',
    'Button', 'Dialog', 'CalendarImportPreviewDialog', 'TimetableRangeEditor', 'rangeErrors', 'rangesValid', 'sortedRanges', 'document', script)(
    computed, nextTick, () => {}, () => {}, ref, () => ({ t: key => key }), axios,
    {}, {}, {}, {}, rangeErrors, rangesValid, sortedRanges, { getElementById: () => null },
  )
  const view = component.setup({ can: () => true }, { expose() {} })
  await view.loadCurrent()
  let [normal, postExam] = view.versions.value
  assert.equal(view.expandedVersionId.value, null)
  view.toggleVersion(normal)
  normal.draft_effective_to = '2027-07-09'
  view.toggleVersion(postExam)
  assert.equal(view.expandedVersionId.value, 2)
  assert.equal(view.versionChanged(normal), true)
  postExam.draft_effective_ranges.push({ effective_from: '2028-01-01', effective_to: '2028-01-10' })
  const moveEvent = { target: { value: '' } }
  await view.selectVersionGroup(moveEvent, postExam)
  assert.equal(moveEvent.target.value, 'move')
  view.selectedGroup.value = null
  assert.equal(view.visibleVersions.value[0].draft_effective_ranges.length, 2)
  view.toggleVersion(postExam)
  assert.equal(view.expandedVersionId.value, null)
  assert.equal(view.versionChanged(postExam), true)
  view.toggleVersion(postExam)
  view.cancelVersion(postExam)
  await nextTick()
  assert.equal(view.expandedVersionId.value, null)
  assert.equal(view.versionChanged(postExam), false)
  assert.equal(postExam.group_id, null, 'cancel leaves the already saved group move intact')
  view.toggleVersion(normal)
  fail = true
  await view.saveVersion(normal)
  assert.equal(view.expandedVersionId.value, 1)
  assert.equal(normal.draft_effective_to, '2027-07-09')
  assert.equal(view.versionSaveError.value, 'importCenter.versionSaveFailed')
  assert.equal(view.busy.value, '')
  fail = false
  postExam.draft_special_subjects.push('體育')
  await view.saveVersion(normal)
  assert.equal(view.expandedVersionId.value, null)
  ;[normal, postExam] = view.versions.value
  assert.equal(view.versionChanged(normal), false)
  assert.equal(normal.effective_to, '2027-07-09')
  assert.deepEqual(postExam.draft_special_subjects, ['體育'], 'saving one row preserves another row’s draft')
  view.toggleVersion(postExam)
  postExam.draft_effective_ranges.push({ effective_from: '2028-01-01', effective_to: '2028-01-10' })
  await view.saveVersion(postExam)
  assert.equal(requests.at(-1).payload.effective_ranges.length, 2)
  assert.deepEqual(requests.at(-1).payload.special_subjects, ['體育'])
  assert.equal(view.versionChanged(view.versions.value[1]), false)
})
