import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { compileScript, parse } from 'vue/compiler-sfc'
import { computed, nextTick, reactive, ref } from 'vue'
import { candidateOptionLabel } from '../src/views/rescheduling/candidateLabel.js'

test('manual date controls the queue and summary, including out-of-order responses', async () => {
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
  const oldTask = { task_key: 'old', target: { date: '2026-06-08' }, absent_teacher_name: '離職老師', candidates: [{ id: 1, name: '舊代課老師' }] }
  const newTask = { task_key: 'new', target: { date: '2026-09-14' }, absent_teacher_name: '新學年老師', candidates: [{ id: 2, name: '新代課老師' }] }
  view.analysis.value = { tasks: [newTask] }
  view.manualTasks.value = [oldTask]
  view.selectManualTask('old')
  const opening = view.openManualPanel('new')
  assert.equal(view.manualDate.value, '2026-09-14')
  assert.equal(view.selectedManualTask.value, undefined)
  assert.equal(view.selectedManualCandidate.value, undefined)
  assert.deepEqual(pending[0].options.params, { data: '2026-09-14' })
  pending[0].resolve({ data: { revision: 1, tasks: [newTask] } })
  await opening
  assert.equal(view.selectedManualCandidate.value.name, '新代課老師')

  view.manualDate.value = '2026-06-08'
  const oldRequest = view.loadManualArrangements()
  view.manualDate.value = '2026-09-14'
  const latestRequest = view.loadManualArrangements()
  pending[2].resolve({ data: { revision: 3, tasks: [newTask] } })
  await latestRequest
  pending[1].resolve({ data: { revision: 2, tasks: [oldTask] } })
  await oldRequest
  assert.equal(view.selectedManualTask.value.absent_teacher_name, '新學年老師')
  assert.equal(view.manualRevision.value, 3)

  view.manualDate.value = ''
  await view.loadManualArrangements()
  assert.equal(pending.length, 3)
  assert.deepEqual(view.manualTasks.value, [])
  assert.equal(view.selectedManualCandidate.value, undefined)
  assert.equal(view.manualLoading.value, false)
})
