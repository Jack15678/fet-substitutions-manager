import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { compileScript, parse } from 'vue/compiler-sfc'
import { computed, nextTick, reactive, ref } from 'vue'
import { candidateOptionLabel } from '../src/views/rescheduling/candidateLabel.js'

test('manual queue separates expired cases and ignores out-of-order responses', async () => {
  const { descriptor } = parse(readFileSync(new URL('../src/views/ReschedulingView.vue', import.meta.url), 'utf8'))
  const script = compileScript(descriptor, { id: 'manual-test' }).content
    .replace(/^import .+$/gm, '').replace('export default', 'return')
  const pending = []
  const axios = { get: (url, options) => new Promise(resolve => pending.push({ url, options, resolve })) }
  const component = new Function('computed', 'nextTick', 'onMounted', 'reactive', 'ref', 'watch',
    'useI18n', 'axios', 'Button', 'Dialog', 'candidateOptionLabel', script)(
    computed, nextTick, () => {}, reactive, ref, () => {},
    () => ({ t: key => key, locale: ref('zh-HK') }), axios, {}, {}, candidateOptionLabel,
  )
  const view = component.setup({ dataGlobal: new Date('2026-09-10T12:00:00'), can: () => true }, { expose() {} })
  const oldTask = { task_key: 'old', expired: true, target: { date: '2026-06-08' }, absent_teacher_name: '離職老師', candidates: [{ id: 1, name: '舊代課老師' }] }
  const newTask = { task_key: 'new', target: { date: '2026-09-14' }, absent_teacher_name: '新學年老師', candidates: [{ id: 2, name: '新代課老師' }] }
  const laterTask = { ...newTask, task_key: 'later', target: { date: '2026-09-21' } }
  const yesterdayTask = { ...oldTask, task_key: 'yesterday', target: { date: '2026-09-09' } }
  const currentResponse = { revision: 1, tasks: [oldTask, yesterdayTask, newTask, laterTask], today: '2026-09-10' }
  view.analysis.value = { tasks: [newTask] }
  view.manualTasks.value = [oldTask]
  view.selectManualScope('expired')
  const opening = view.openManualPanel('new')
  assert.equal(view.selectedManualTask.value, undefined)
  assert.equal(view.selectedManualCandidate.value, undefined)
  assert.equal(pending[0].options.params, undefined)
  pending[0].resolve({ data: currentResponse })
  await opening
  assert.equal(view.manualScope.value, 'pending')
  assert.equal(view.manualToday.value, '2026-09-10')
  assert.deepEqual(view.manualScopeCounts.value, { pending: 2, expired: 2 })
  assert.deepEqual(view.visibleManualTasks.value.map(task => task.target.date), ['2026-09-14', '2026-09-21'])
  view.selectManualScope('expired')
  assert.equal(view.selectedManualTask.value.task_key, 'old')
  assert.equal(view.visibleManualTasks.value.length, 2)
  view.selectManualScope('pending')
  view.selectManualTask('later')
  assert.equal(view.selectedManualTask.value.target.date, '2026-09-21')
  assert.equal(view.selectedManualCandidate.value.name, '新代課老師')

  const oldRequest = view.loadManualArrangements()
  assert.equal(view.selectedManualTask.value, undefined)
  const latestRequest = view.loadManualArrangements()
  pending[2].resolve({ data: { ...currentResponse, revision: 3 } })
  await latestRequest
  pending[1].resolve({ data: { revision: 2, tasks: [oldTask], today: '2026-09-09' } })
  await oldRequest
  assert.equal(view.selectedManualTask.value.absent_teacher_name, '新學年老師')
  assert.equal(view.manualRevision.value, 3)

  assert.equal(view.manualTasks.value.length, 4)
  assert.equal(view.manualLoading.value, false)
  // A generic opening must use the current context, not a previously viewed historical analysis.
  view.analysis.value = { tasks: [oldTask] }
  view.selectedAnalysisDate.value = '2026-06-08'
  const reopen = view.openManualPanel()
  assert.equal(pending[3].options.params, undefined)
  pending[3].resolve({ data: currentResponse })
  await reopen
  // Opening a particular historical case selects the expired category for optional backfilling.
  const historicalOpening = view.openManualPanel('old')
  pending[4].resolve({ data: currentResponse })
  await historicalOpening
  assert.equal(view.manualScope.value, 'expired')
  assert.equal(view.selectedManualTask.value.task_key, 'old')
})
