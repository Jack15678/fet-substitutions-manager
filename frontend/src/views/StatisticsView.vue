<template>
  <section class="statistics-page">
    <header class="page-heading">
      <h2>{{ $t('statistics.matrixTitle') }}</h2>
      <p>{{ $t('statistics.matrixHint') }}</p>
    </header>

    <section class="panel">
      <div class="filters">
        <label class="search-field">
          <span>{{ $t('statistics.search') }}</span>
          <span class="search-input">
            <i class="pi pi-search" aria-hidden="true"></i>
            <input v-model="search" type="search" :placeholder="$t('statistics.searchPlaceholder')" />
          </span>
        </label>
        <form class="range-form" @submit.prevent="loadStatistics">
          <label>{{ $t('statistics.startDate') }}<input v-model="startDate" type="date" :max="endDate || undefined" required /></label>
          <label>{{ $t('statistics.endDate') }}<input v-model="endDate" type="date" :min="startDate || undefined" required /></label>
          <Button type="submit" :label="$t('statistics.apply')" :loading="loading" :disabled="loading" />
        </form>
      </div>
      <Transition name="motion-fade"><p v-if="error" class="field-error" role="alert">{{ error }}</p></Transition>
      <div class="result-bar">
        <p role="status">
          <span v-if="statistics.range" class="queried-range">{{ statistics.range.start_date.replaceAll('-', '/') }} – {{ statistics.range.end_date.replaceAll('-', '/') }}</span>
          <span v-if="!loading">{{ search.trim() ? $t('statistics.filteredCount', { count: filteredTeachers.length, total: statistics.teachers.length }) : $t('statistics.teacherCount', { count: statistics.teachers.length }) }}</span>
        </p>
        <label class="months-toggle"><input v-model="showAllMonths" type="checkbox" />{{ $t('statistics.showAllMonths') }}</label>
      </div>
      <Transition name="motion-fade" mode="out-in">
        <div v-if="loading" class="empty-state" role="status">{{ $t('common.loading') }}</div>
        <div v-else-if="!filteredTeachers.length" class="empty-state">
          <p>{{ search.trim() && statistics.teachers.length ? $t('statistics.noResults', { query: search.trim() }) : $t('common.noData') }}</p>
          <Button v-if="search" type="button" :label="$t('statistics.clearSearch')" text @click="search = ''" />
        </div>
        <div v-else class="table-wrap" role="region" :aria-label="$t('statistics.matrixTitle')" tabindex="0">
          <table>
            <thead><tr><th scope="col">{{ $t('statistics.teacher') }}</th><th v-for="month in visibleMonths" :key="month" scope="col">{{ monthLabel(month) }}</th><th scope="col" class="total">{{ $t('statistics.total') }}</th></tr></thead>
            <tbody>
              <tr v-for="teacher in filteredTeachers" :key="teacher.id">
                <th scope="row">{{ teacher.name }}</th><td v-for="month in visibleMonths" :key="month" :class="{ zero: teacher.monthly[month] === 0 }">{{ teacher.monthly[month] }}</td><td class="total">{{ teacher.total }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </Transition>
    </section>

  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import axios from 'axios'
import Button from 'primevue/button'

const props = defineProps({ dataGlobal: Date })
const { locale, t } = useI18n()
const selectedYear = (props.dataGlobal || new Date()).getFullYear()
const startDate = ref(`${selectedYear}-01-01`)
const endDate = ref(`${selectedYear}-12-31`)
const statistics = ref({ months: [], teachers: [] })
const loading = ref(false)
const error = ref('')
const search = ref('')
const showAllMonths = ref(false)

const filteredTeachers = computed(() => {
  const query = search.value.trim().toLocaleLowerCase()
  return statistics.value.teachers.filter(teacher => teacher.name.toLocaleLowerCase().includes(query))
})
const visibleMonths = computed(() => statistics.value.months.filter(month => showAllMonths.value
  || statistics.value.teachers.some(teacher => teacher.monthly[month] > 0)))
const sameYear = computed(() => new Set(statistics.value.months.map(month => month.slice(0, 4))).size <= 1)
const monthLabel = (month) => new Intl.DateTimeFormat(locale.value === 'en' ? 'en-HK' : 'zh-HK', {
  year: sameYear.value ? undefined : 'numeric', month: 'short'
}).format(new Date(`${month}-01T12:00:00`))

const loadStatistics = async () => {
  error.value = ''
  if (!startDate.value || !endDate.value || startDate.value > endDate.value) {
    error.value = t('statistics.invalidRange')
    return
  }
  loading.value = true
  try {
    statistics.value = (await axios.get('/api/rescheduling/statistics', {
      params: { start_date: startDate.value, end_date: endDate.value }
    })).data
    statistics.value.teachers = statistics.value.teachers.filter(teacher => teacher.total > 0)
  }
  catch (requestError) {
    error.value = requestError.response?.data?.detail || t('statistics.loadError')
  }
  finally { loading.value = false }
}

onMounted(loadStatistics)
</script>

<style scoped>
.statistics-page { display: grid; gap: 1.25rem; color: var(--text-color-primary); }
.page-heading h2 { margin: 0; font-size: clamp(1.65rem, 3vw, 2.15rem); letter-spacing: -.035em; }
.page-heading p { margin: .3rem 0 0; color: var(--text-color-secondary); font-size: var(--font-ui); }
.panel { min-width: 0; padding: 1.25rem; border: 1px solid var(--border-color); border-radius: var(--radius-md); background: var(--card-background); }
.filters { display: flex; align-items: flex-end; justify-content: space-between; gap: 1.25rem; flex-wrap: wrap; }
.filters label { display: flex; min-width: 0; flex-direction: column; gap: .35rem; color: var(--text-color-secondary); font-size: var(--font-ui); font-weight: 500; }
.search-field { flex: 1 1 15rem; max-width: 24rem; }
.search-input { position: relative; display: flex; }
.search-input i { position: absolute; left: .8rem; top: 50%; transform: translateY(-50%); pointer-events: none; }
.filters input { width: 100%; min-width: 0; min-height: 2.75rem; padding: .55rem .65rem; border: 1px solid var(--border-strong); border-radius: var(--radius-sm); background: var(--card-background); color: var(--text-color-primary); font: inherit; }
.search-input input { padding-left: 2.3rem; }
.range-form { display: flex; align-items: flex-end; gap: .6rem; }
.range-form :deep(.p-button) { min-height: 2.75rem; font-size: var(--font-ui); }
.result-bar { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: .5rem 1rem; margin: 1.1rem 0 .65rem; color: var(--text-color-secondary); font-size: var(--font-supporting); }
.result-bar p { display: flex; flex-wrap: wrap; gap: .35rem 1rem; margin: 0; }
.queried-range { font-variant-numeric: tabular-nums; }
.months-toggle { display: flex; align-items: center; gap: .45rem; min-height: 2rem; cursor: pointer; }
.months-toggle input { width: 1rem; height: 1rem; accent-color: var(--primary-color); }
.filters input:focus-visible, .months-toggle input:focus-visible, .table-wrap:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
.field-error { margin-top: 1rem; padding: .75rem .9rem; border-radius: var(--radius-sm); background: #fff0f0; color: #a12626; }
.table-wrap { overflow: auto; max-height: 65vh; border: 1px solid var(--border-color); border-radius: var(--radius-sm); }
table { width: 100%; border-collapse: separate; border-spacing: 0; font-size: var(--font-data); font-variant-numeric: tabular-nums; }
th, td { min-width: 4.5rem; padding: .55rem .8rem; border-bottom: 1px solid var(--border-color); text-align: center; white-space: nowrap; }
thead th { position: sticky; top: 0; z-index: 2; background: var(--surface-soft); color: var(--text-color-secondary); font-size: var(--font-ui); font-weight: 500; }
tr > :first-child { position: sticky; left: 0; min-width: 8rem; text-align: left; }
thead th:first-child { z-index: 3; }
tbody th { z-index: 1; background: var(--card-background); font-weight: 600; }
tbody td { font-weight: 500; }
tbody .zero { color: var(--text-color-secondary); font-weight: 400; }
tbody tr:hover > * { background: var(--surface-soft); }
.total { position: sticky; right: 0; background: var(--highlight-bg); color: var(--primary-color-dark); font-weight: 700; border-left: 1px solid var(--border-color); }
tbody .total { z-index: 1; }
tbody tr:hover .total { background: var(--primary-color-light); }
tbody tr:last-child > * { border-bottom: 0; }
.empty-state { display: grid; justify-items: center; gap: .5rem; padding: 3rem 1rem; border-top: 1px solid var(--border-color); color: var(--text-color-secondary); text-align: center; overflow-wrap: anywhere; }
@media (max-width: 800px) {
  .search-field { max-width: none; flex-basis: 100%; }
  .range-form { width: 100%; }
  .range-form label { flex: 1; }
}
@media (max-width: 480px) {
  .panel { padding: .85rem; }
  .range-form { display: grid; grid-template-columns: minmax(0, 1fr); }
  .range-form :deep(.p-button) { grid-column: 1 / -1; justify-content: center; }
}
</style>
