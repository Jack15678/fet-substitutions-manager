<template>
  <section class="statistics-page">
    <header class="page-heading">
      <div><h2>{{ $t('statistics.title') }}</h2><p>{{ $t('statistics.description') }}</p></div>
    </header>

    <section class="panel">
      <div class="panel-title">
        <div><h3>{{ $t('statistics.matrixTitle') }}</h3><p>{{ $t('statistics.matrixHint') }}</p></div>
        <form class="range-form" @submit.prevent="loadStatistics">
          <label>{{ $t('statistics.startDate') }}<input v-model="startDate" type="date" required /></label>
          <label>{{ $t('statistics.endDate') }}<input v-model="endDate" type="date" required /></label>
          <Button type="submit" :label="$t('statistics.apply')" icon="pi pi-search" :loading="loading" />
        </form>
      </div>
      <p v-if="error" class="field-error" role="alert">{{ error }}</p>
      <div v-if="loading" class="empty-state">{{ $t('common.loading') }}</div>
      <div v-else class="table-wrap">
        <table>
          <thead><tr><th>{{ $t('statistics.teacher') }}</th><th v-for="month in statistics.months" :key="month">{{ monthLabel(month) }}</th><th>{{ $t('statistics.total') }}</th></tr></thead>
          <tbody>
            <tr v-for="teacher in statistics.teachers" :key="teacher.id">
              <th>{{ teacher.name }}</th><td v-for="month in statistics.months" :key="month">{{ teacher.monthly[month] }}</td><td class="total">{{ teacher.total }}</td>
            </tr>
            <tr v-if="!statistics.teachers.length"><td :colspan="statistics.months.length + 2" class="empty-row">{{ $t('common.noData') }}</td></tr>
          </tbody>
        </table>
      </div>
    </section>

  </section>
</template>

<script setup>
import { onMounted, ref } from 'vue'
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

const monthLabel = (month) => new Intl.DateTimeFormat(locale.value === 'en' ? 'en-HK' : 'zh-HK', { year: '2-digit', month: 'short' }).format(new Date(`${month}-01T12:00:00`))

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
.page-heading h2, h3 { margin: 0; }
.page-heading h2 { font-size: clamp(1.65rem, 3vw, 2.15rem); letter-spacing: -.035em; }
.page-heading p, .panel-title p { margin-top: .3rem; color: var(--text-color-secondary); }
.panel { min-width: 0; padding: 1.25rem; border: 1px solid var(--border-color); border-radius: 12px; background: var(--card-background); }
.panel-title { display: flex; justify-content: space-between; gap: 1rem; align-items: flex-end; margin-bottom: 1rem; }
label { display: flex; flex-direction: column; gap: .35rem; color: #344054; font-size: var(--font-ui); font-weight: 650; }
input { min-height: 2.5rem; padding: .55rem .65rem; border: 1px solid #cfd6df; border-radius: 8px; background: #fff; color: var(--text-color-primary); }
.range-form { display: flex; align-items: flex-end; gap: .6rem; }
.field-error { margin: 0 0 1rem; padding: .75rem .9rem; border-radius: 8px; background: #fff0f0; color: #a12626; }
.table-wrap { overflow: auto; border: 1px solid var(--border-color); border-radius: 10px; }
table { width: 100%; min-width: 1000px; border-collapse: collapse; font-size: var(--font-data); }
th, td { padding: .65rem .7rem; border-bottom: 1px solid #edf0f3; text-align: center; white-space: nowrap; }
thead th { position: sticky; top: 0; background: var(--surface-soft); color: var(--text-color-secondary); }
tbody th { position: sticky; left: 0; background: #fff; text-align: left; }
tbody tr:hover th, tbody tr:hover td { background: #fbfcfe; }
.total { background: var(--highlight-bg); color: var(--primary-color-dark); font-weight: 750; }
.empty-state, .empty-row { padding: 2rem; color: var(--text-color-secondary); text-align: center; }
@media (max-width: 800px) { .panel-title, .range-form { align-items: stretch; flex-direction: column; } }
</style>
