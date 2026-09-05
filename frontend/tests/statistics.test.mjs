import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { compileScript, parse } from 'vue/compiler-sfc'
import { computed, ref } from 'vue'

test('teacher search and month visibility preserve the queried statistics', async () => {
  const source = readFileSync(new URL('../src/views/StatisticsView.vue', import.meta.url), 'utf8')
  const { descriptor } = parse(source)
  const script = compileScript(descriptor, { id: 'statistics-test' }).content
    .replace(/^import .+$/gm, '').replace('export default', 'return')
  const data = {
    range: { start_date: '2026-01-01', end_date: '2026-12-31' },
    months: ['2026-01', '2026-02', '2026-03'],
    teachers: [
      { id: 1, name: '何燕玉', total: 2, monthly: { '2026-01': 2, '2026-02': 0, '2026-03': 0 } },
      { id: 2, name: 'Alex Chan', total: 1, monthly: { '2026-01': 0, '2026-02': 0, '2026-03': 1 } },
      { id: 3, name: '未有記錄', total: 0, monthly: { '2026-01': 0, '2026-02': 0, '2026-03': 0 } },
    ],
  }
  let mount, fail = false
  const requests = []
  const axios = { get: async (url, options) => {
    requests.push({ url, ...options })
    if (fail) throw new Error('offline')
    return { data: structuredClone(data) }
  } }
  const locale = ref('zh-HK')
  const component = new Function('computed', 'onMounted', 'ref', 'useI18n', 'axios', 'Button', script)(
    computed, callback => { mount = callback }, ref, () => ({ locale, t: key => key }), axios, {},
  )
  const view = component.setup({ dataGlobal: new Date('2026-05-01T12:00:00') }, { expose() {} })
  await mount()
  assert.deepEqual(requests[0], { url: '/api/rescheduling/statistics', params: { start_date: '2026-01-01', end_date: '2026-12-31' } })
  assert.equal(view.filteredTeachers.value.length, 2)
  assert.deepEqual(view.visibleMonths.value, ['2026-01', '2026-03'])
  view.search.value = ' 燕 '
  assert.deepEqual(view.filteredTeachers.value.map(row => row.id), [1])
  assert.equal(view.filteredTeachers.value[0].total, 2)
  assert.deepEqual(view.visibleMonths.value, ['2026-01', '2026-03'])
  view.search.value = ' aLeX '
  assert.deepEqual(view.filteredTeachers.value.map(row => row.id), [2])
  view.search.value = '不存在'
  assert.equal(view.filteredTeachers.value.length, 0)
  view.search.value = '   '
  assert.equal(view.filteredTeachers.value.length, 2)
  view.showAllMonths.value = true
  assert.deepEqual(view.visibleMonths.value, data.months)
  assert.equal(requests.length, 1, 'search and display changes must not refetch')
  assert.equal(view.monthLabel('2026-01'), '1月')
  locale.value = 'en'
  assert.equal(view.monthLabel('2026-01'), 'Jan')
  view.statistics.value.months = ['2025-12', '2026-01']
  assert.match(view.monthLabel('2025-12'), /2025/)
  assert.match(view.monthLabel('2026-01'), /2026/)
  view.startDate.value = '2027-01-01'
  await view.loadStatistics()
  assert.equal(requests.length, 1)
  assert.equal(view.error.value, 'statistics.invalidRange')
  view.startDate.value = '2026-01-01'
  fail = true
  await view.loadStatistics()
  assert.equal(view.error.value, 'statistics.loadError')
  assert.equal(view.loading.value, false)
  assert.deepEqual(view.statistics.value.range, data.range)
  fail = false
  data.teachers = []
  await view.loadStatistics()
  view.showAllMonths.value = false
  assert.equal(view.filteredTeachers.value.length, 0)
  assert.deepEqual(view.visibleMonths.value, [])
  assert.equal(view.error.value, '')
})
