<template>
  <section class="import-page">
    <header class="page-heading">
      <div>
        <p class="eyebrow">{{ $t('importCenter.eyebrow') }}</p>
        <h2>{{ $t('importCenter.title') }}</h2>
        <p>{{ $t('importCenter.description') }}</p>
      </div>
      <span class="revision">{{ $t('rescheduling.revision', { revision: timetable.revision ?? '—' }) }}</span>
    </header>

    <section class="panel">
      <h3>{{ $t('importCenter.baseTitle') }}</h3>
      <div class="import-grid">
        <label>{{ $t('importCenter.classFile') }}<input type="file" accept=".xls" @change="classFile = $event.target.files[0]" /></label>
        <label>{{ $t('importCenter.teacherFile') }}<input type="file" accept=".xlsx" @change="teacherFile = $event.target.files[0]" /></label>
        <label>{{ $t('importCenter.effectiveFrom') }}<input v-model="effectiveFrom" type="date" /></label>
        <label>{{ $t('importCenter.effectiveTo') }}<input v-model="effectiveTo" type="date" /></label>
        <Button :label="$t('importCenter.check')" icon="pi pi-search" :loading="busy === 'preview'" :disabled="!classFile || !teacherFile || !effectiveFrom || !effectiveTo" @click="previewImport" />
      </div>
      <p v-if="timetable.active" class="muted">{{ $t('importCenter.currentFiles', { date: timetable.query_date, classFile: timetable.class_filename, teacherFile: timetable.teacher_filename }) }}</p>
      <p v-else class="notice warning">{{ $t('importCenter.noCurrent') }}</p>
    </section>

    <section class="panel">
      <div class="result-heading">
        <div><h3>{{ $t('importCenter.versionsTitle') }}</h3><p class="muted">{{ $t('importCenter.versionsHint') }}</p></div>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>{{ $t('importCenter.startDate') }}</th><th>{{ $t('importCenter.endDate') }}</th><th>{{ $t('importCenter.files') }}</th><th>{{ $t('importCenter.scale') }}</th><th>{{ $t('importCenter.linkedRecords') }}</th><th>{{ $t('importCenter.status') }}</th><th>{{ $t('importCenter.actions') }}</th></tr></thead>
          <tbody>
            <tr v-for="version in versions" :key="version.id">
              <td><input v-model="version.draft_effective_from" type="date" /></td>
              <td><input v-model="version.draft_effective_to" type="date" /></td>
              <td><div class="file-list"><span>{{ version.class_filename }}</span><span>{{ version.teacher_filename }}</span></div></td>
              <td>{{ $t('importCenter.scaleValue', { lessons: version.lessons, teachers: version.teachers }) }}</td>
              <td>{{ $t('importCenter.recordValue', { absences: version.absence_records, adjustments: version.adjustment_records }) }}</td>
              <td><span :class="['status', version.locked ? 'locked' : 'available']">{{ version.locked ? $t('importCenter.locked') : $t('importCenter.available') }}</span><span v-if="version.is_current" class="status current">{{ $t('importCenter.current') }}</span></td>
              <td><div class="version-actions"><Button :label="$t('common.save')" size="small" :loading="busy === `version-${version.id}`" :disabled="!version.draft_effective_from || !version.draft_effective_to || (version.draft_effective_from === version.effective_from && version.draft_effective_to === version.effective_to)" @click="saveVersion(version)" /><Button :label="$t('common.delete')" size="small" severity="danger" outlined :disabled="version.locked" @click="removeVersion(version)" /></div></td>
            </tr>
            <tr v-if="!versions.length"><td colspan="7" class="empty-row">{{ $t('importCenter.noVersions') }}</td></tr>
          </tbody>
        </table>
      </div>
    </section>

    <template v-if="preview">
      <section class="summary-grid">
        <div><strong>{{ preview.classes }}</strong><span>{{ $t('importCenter.classes') }}</span></div>
        <div><strong>{{ preview.teachers }}</strong><span>{{ $t('importCenter.teachers') }}</span></div>
        <div><strong>{{ preview.lessons }}</strong><span>{{ $t('importCenter.lessons') }}</span></div>
        <div :class="{ alert: preview.blocked_lessons }"><strong>{{ preview.blocked_lessons }}</strong><span>{{ $t('importCenter.blocked') }}</span></div>
      </section>

      <section class="panel">
        <div class="result-heading">
          <div><h3>{{ $t('importCenter.resultTitle') }}</h3><p class="muted">{{ $t('importCenter.resultHint') }}</p></div>
          <Button :label="$t('importCenter.activate')" icon="pi pi-check" severity="success" :loading="busy === 'activate'" :disabled="hasErrors || !effectiveFrom || !effectiveTo" @click="activateImport" />
        </div>
        <ul v-if="preview.warnings.length" class="warnings">
          <li v-for="warning in preview.warnings" :key="warning">{{ warning }}</li>
        </ul>
        <p v-if="hasErrors" class="notice danger">{{ $t('importCenter.errorsBlock') }}</p>
        <div class="table-wrap">
          <table>
            <thead><tr><th>{{ $t('importCenter.severity') }}</th><th>{{ $t('importCenter.weekdayPeriod') }}</th><th>{{ $t('rescheduling.class') }}</th><th>{{ $t('rescheduling.subject') }}</th><th>{{ $t('rescheduling.teacherColumn') }}</th><th>{{ $t('importCenter.classWorkbook') }}</th><th>{{ $t('importCenter.teacherWorkbook') }}</th></tr></thead>
            <tbody>
              <tr v-for="(issue, index) in preview.issues" :key="index">
                <td><span :class="['status', issue.severity]">{{ issue.severity === 'error' ? $t('common.error') : $t('importCenter.review') }}</span></td>
                <td>{{ weekdayLabel(issue.weekday) }} {{ $t('records.period', { period: issue.period }) }}</td>
                <td>{{ issue.class_code }}</td><td>{{ issue.subject }}</td><td>{{ issue.teacher || '—' }}</td>
                <td>{{ issue.class_workbook }}</td><td>{{ issue.teacher_workbook }}</td>
              </tr>
              <tr v-if="!preview.issues.length"><td colspan="7" class="empty-row">{{ $t('importCenter.perfectMatch') }}</td></tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>

    <p v-if="message" class="notice success">{{ message }}</p>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import axios from 'axios'
import Button from 'primevue/button'

const { t } = useI18n()

const timetable = ref({ active: false })
const versions = ref([])
const classFile = ref(null)
const teacherFile = ref(null)
const effectiveFrom = ref('')
const effectiveTo = ref('')
const preview = ref(null)
const busy = ref('')
const message = ref('')
const hasErrors = computed(() => preview.value?.issues.some(issue => issue.severity === 'error'))

const loadCurrent = async () => {
  const [currentResponse, versionsResponse] = await Promise.all([
    axios.get('/api/timetables/current'), axios.get('/api/timetables')
  ])
  timetable.value = currentResponse.data
  versions.value = versionsResponse.data.map(version => ({
    ...version, draft_effective_from: version.effective_from, draft_effective_to: version.effective_to || ''
  }))
}

const saveVersion = async (version) => {
  busy.value = `version-${version.id}`; message.value = ''
  try {
    await axios.put(`/api/timetables/${version.id}`, {
      effective_from: version.draft_effective_from, effective_to: version.draft_effective_to
    })
    message.value = t('importCenter.versionUpdated')
    await loadCurrent()
  } finally { busy.value = '' }
}

const removeVersion = async (version) => {
  if (!window.confirm(t('importCenter.deleteConfirm', { date: version.effective_from }))) return
  await axios.delete(`/api/timetables/${version.id}`)
  message.value = t('importCenter.versionDeleted')
  await loadCurrent()
}

const previewImport = async () => {
  busy.value = 'preview'; message.value = ''
  try {
    const form = new FormData()
    form.append('class_workbook', classFile.value)
    form.append('teacher_workbook', teacherFile.value)
    preview.value = (await axios.post('/api/timetables/import/preview', form)).data
  } finally { busy.value = '' }
}

const activateImport = async () => {
  busy.value = 'activate'; message.value = ''
  try {
    await axios.post(`/api/timetables/import/${preview.value.preview_id}/activate`, {
      effective_from: effectiveFrom.value, effective_to: effectiveTo.value
    })
    message.value = t('importCenter.activated', { start: effectiveFrom.value, end: effectiveTo.value })
    preview.value = null
    await loadCurrent()
  } finally { busy.value = '' }
}

const weekdayLabel = (weekday) => t(`importCenter.weekdays.${weekday}`, `${weekday}`)

onMounted(loadCurrent)
</script>

<style scoped>
.import-page{display:flex;flex-direction:column;gap:1.25rem;color:#172033}.page-heading,.result-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:1.5rem}.page-heading h2{font-size:2rem;margin:.15rem 0}.page-heading p,.muted{color:#657084}.eyebrow{color:#4965d6!important;font-weight:700;text-transform:uppercase;font-size:.78rem;letter-spacing:.08em}.revision{background:#eef2ff;color:#4256b5;padding:.5rem .75rem;border-radius:999px;font-size:.82rem;white-space:nowrap}.panel{background:#fff;border:1px solid #e4e8f0;border-radius:14px;padding:1.2rem;box-shadow:0 4px 18px rgba(35,45,75,.05)}.panel h3{margin:0 0 .9rem}.result-heading h3{margin:0}.import-grid{display:grid;grid-template-columns:1fr 1fr .65fr auto;align-items:end;gap:.8rem}.import-grid label{display:flex;flex-direction:column;gap:.35rem;font-size:.84rem;font-weight:600}input{width:100%;border:1px solid #ccd3df;border-radius:8px;padding:.6rem;background:#fff}.summary-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:1rem}.summary-grid div{display:flex;flex-direction:column;background:#fff;border:1px solid #e4e8f0;border-radius:12px;padding:1rem}.summary-grid strong{font-size:1.8rem}.summary-grid span{color:#657084}.summary-grid .alert{border-color:#e6bd79;background:#fff9ef}.warnings{margin:.9rem 0;padding-left:1.2rem;color:#87591d}.table-wrap{overflow:auto;margin-top:1rem}table{width:100%;border-collapse:collapse;font-size:.86rem}th,td{text-align:left;padding:.68rem;border-bottom:1px solid #edf0f4;white-space:nowrap}th{color:#657084;background:#fafbfc}.file-list{display:flex;flex-direction:column;gap:.2rem;max-width:260px}.file-list span{overflow:hidden;text-overflow:ellipsis}.version-actions{display:flex;gap:.4rem}.status{display:inline-block;font-size:.75rem;padding:.25rem .5rem;border-radius:999px;background:#fff0d8;color:#86540f}.status+.status{margin-left:.35rem}.status.error,.status.locked{background:#feeceb;color:#a43a31}.status.available{background:#eaf8f0;color:#247147}.status.current{background:#eef2ff;color:#4256b5}.notice{padding:.8rem 1rem;border-radius:9px}.warning{background:#fff7e6;color:#8a5b16}.danger{background:#feeceb;color:#96382f}.success{background:#eaf8f0;color:#247147}.empty-row{text-align:center;color:#8490a3}@media(max-width:850px){.import-grid,.summary-grid{grid-template-columns:1fr 1fr}}@media(max-width:560px){.page-heading,.result-heading{flex-direction:column}.import-grid,.summary-grid{grid-template-columns:1fr}}
.import-grid{grid-template-columns:1fr 1fr .55fr .55fr auto}
</style>
