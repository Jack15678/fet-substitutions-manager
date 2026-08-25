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

    <section class="panel export-panel">
      <div><h3>{{ $t('statistics.exportTitle') }}</h3><p>{{ $t('statistics.exportHint') }}</p></div>
      <label>{{ $t('statistics.exportDate') }}<input v-model="exportDate" type="date" /></label>
      <div class="actions">
        <Button :label="$t('statistics.exportExcel')" icon="pi pi-file-excel" :loading="busy === 'xlsx'" @click="download('xlsx')" />
        <Button :label="$t('statistics.exportPdf')" icon="pi pi-file-pdf" severity="danger" :loading="busy === 'pdf'" @click="download('pdf')" />
      </div>
    </section>
  </section>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import axios from 'axios'
import Button from 'primevue/button'

const props = defineProps({ dataGlobal: Date })
const { locale, t } = useI18n()
const iso = (value) => {
  const date = value || new Date()
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000)
  return local.toISOString().slice(0, 10)
}
const selectedYear = (props.dataGlobal || new Date()).getFullYear()
const startDate = ref(`${selectedYear}-01-01`)
const endDate = ref(`${selectedYear}-12-31`)
const statistics = ref({ months: [], teachers: [] })
const exportDate = ref(iso(props.dataGlobal))
const loading = ref(false)
const busy = ref('')
const error = ref('')

watch(() => props.dataGlobal, value => { exportDate.value = iso(value) })
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

const download = async (format) => {
  busy.value = format
  try {
    const response = await axios.get(`/api/rescheduling/exports/daily.${format}`, { params: { data: exportDate.value }, responseType: 'blob' })
    const disposition = response.headers['content-disposition'] || ''
    const fallbackExtension = response.headers['content-type'] === 'application/zip' ? 'zip' : format
    const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1] || `daily-substitution-${exportDate.value}.${fallbackExtension}`
    const url = URL.createObjectURL(response.data)
    const link = document.createElement('a')
    link.href = url; link.download = filename; link.click()
    URL.revokeObjectURL(url)
  } finally { busy.value = '' }
}

onMounted(loadStatistics)
</script>

<style scoped>
.statistics-page { display: grid; gap: 1.25rem; color: var(--text-color-primary); }
.page-heading h2, h3 { margin: 0; }
.page-heading h2 { font-size: clamp(1.65rem, 3vw, 2.15rem); letter-spacing: -.035em; }
.page-heading p, .panel-title p, .export-panel p { margin-top: .3rem; color: var(--text-color-secondary); }
.panel { min-width: 0; padding: 1.25rem; border: 1px solid var(--border-color); border-radius: 12px; background: var(--card-background); }
.panel-title { display: flex; justify-content: space-between; gap: 1rem; align-items: flex-end; margin-bottom: 1rem; }
label { display: flex; flex-direction: column; gap: .35rem; color: #344054; font-size: .84rem; font-weight: 650; }
input { min-height: 2.5rem; padding: .55rem .65rem; border: 1px solid #cfd6df; border-radius: 8px; background: #fff; color: var(--text-color-primary); }
.range-form { display: flex; align-items: flex-end; gap: .6rem; }
.field-error { margin: 0 0 1rem; padding: .75rem .9rem; border-radius: 8px; background: #fff0f0; color: #a12626; }
.table-wrap { overflow: auto; border: 1px solid var(--border-color); border-radius: 10px; }
table { width: 100%; min-width: 900px; border-collapse: collapse; font-size: .82rem; }
th, td { padding: .65rem .7rem; border-bottom: 1px solid #edf0f3; text-align: center; white-space: nowrap; }
thead th { position: sticky; top: 0; background: var(--surface-soft); color: var(--text-color-secondary); }
tbody th { position: sticky; left: 0; background: #fff; text-align: left; }
tbody tr:hover th, tbody tr:hover td { background: #fbfcfe; }
.total { background: var(--highlight-bg); color: var(--primary-color-dark); font-weight: 750; }
.export-panel { display: grid; grid-template-columns: 1fr minmax(220px, .35fr) auto; align-items: end; gap: 1rem; }
.actions { display: flex; justify-content: flex-end; gap: .6rem; }
.empty-state, .empty-row { padding: 2rem; color: var(--text-color-secondary); text-align: center; }
@media (max-width: 800px) { .panel-title, .export-panel, .range-form { align-items: stretch; grid-template-columns: 1fr; flex-direction: column; } .actions { justify-content: flex-start; } }
</style>
