import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { compileScript, parse } from 'vue/compiler-sfc'
import { computed, reactive, ref } from 'vue'
import { createI18n } from 'vue-i18n'

test('date groups and compact periods preserve records, filters and detail selection across pages', async () => {
  const { descriptor } = parse(readFileSync(new URL('../src/views/RecordsView.vue', import.meta.url), 'utf8'))
  const script = compileScript(descriptor, { id: 'records-test' }).content
    .replace(/^import .+$/gm, '').replace('export default', 'return')
  const messages = Object.fromEntries(['zh-HK', 'en'].map(locale => [locale,
    JSON.parse(readFileSync(new URL(`../src/locales/${locale}.json`, import.meta.url), 'utf8'))]))
  const i18n = createI18n({ legacy: false, locale: 'zh-HK', messages })
  const items = [
    { id: 'absence-1', date: '2026-06-10', teacher_name: '周倩儀' },
    { id: 'absence-2', date: '2026-05-21', teacher_name: '劉慧妍' },
    ...['高君琦', '吳淑君', '吳晶晶'].map((name, index) => ({ id: `absence-${index + 3}`, date: '2026-05-20', teacher_name: name })),
    { id: 'adjustment-1', date: '2025-12-11', teacher_name: null },
  ]
  let response = { page: 1, pages: 2, total: 21, items }
  const requests = []
  const axios = { get: async (url, options) => { requests.push({ url, ...options }); return { data: response } } }
  const component = new Function('computed', 'onMounted', 'reactive', 'ref', 'useI18n', 'axios', 'Button', 'Sidebar', script)(
    computed, () => {}, reactive, ref, () => i18n.global, axios, {}, {},
  )
  const view = component.setup({ can: () => false }, { expose() {}, emit() {} })
  await view.loadRecords()
  assert.deepEqual(view.groupedRecords.value.map(group => [group.date, group.items.length]), [
    ['2026-06-10', 1], ['2026-05-21', 1], ['2026-05-20', 3], ['2025-12-11', 1],
  ])
  assert.deepEqual(view.groupedRecords.value.flatMap(group => group.items), items)
  assert.equal(view.periodsLabel({ periods: [1] }), '第 1 節')
  const periods = [6, 1, 3, 2, 6, 7, 9]
  assert.equal(view.periodsLabel({ periods }), '第 1–3 節、第 6–7 節、第 9 節')
  assert.deepEqual(periods, [6, 1, 3, 2, 6, 7, 9])
  assert.equal(view.periodsLabel({ periods: [1, 2, 3, 4, 5, 6, 7, 8] }), '第 1–8 節')
  assert.equal(view.periodsLabel({ periods: [1, 2, 3, 4, 5, 6, 7, 8, 9] }), '全天缺席')
  assert.equal(view.periodsLabel({ periods: [] }), '—')
  i18n.global.locale.value = 'en'
  assert.equal(view.periodsLabel({ periods: [1, 2, 3, 5] }), 'Periods 1–3, Period 5')
  const selected = view.groupedRecords.value[2].items[1]
  view.openDetail(selected)
  assert.equal(view.selectedRecord.value.id, 'absence-4')
  assert.equal(view.detailVisible.value, true)
  Object.assign(view.filters, { q: '吳', date_from: '2026-05-01', date_to: '2026-05-31', status: 'completed', kind: 'swap' })
  response = { page: 2, pages: 2, total: 21, items: [{ id: 'absence-21', date: '2026-05-20' }] }
  await view.loadRecords(2)
  assert.deepEqual(requests.at(-1), { url: '/api/records', params: { scope: 'all', page: 2, page_size: 20, ...view.filters } })
  assert.deepEqual(view.groupedRecords.value.map(group => group.items.map(record => record.id)), [['absence-21']])
  assert.equal(view.detailVisible.value, false)
  response = { page: 1, pages: 1, total: 0, items: [] }
  await view.loadRecords(1)
  assert.deepEqual(view.groupedRecords.value, [])
})
