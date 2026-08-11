<template>
  <section class="rescheduling-page">
    <header class="page-heading">
      <div>
        <p class="eyebrow">{{ $t('rescheduling.eyebrow') }}</p>
        <h2>{{ $t('rescheduling.title') }}</h2>
        <p>{{ $t('rescheduling.description') }}</p>
      </div>
      <span class="revision">{{ $t('rescheduling.revision', { revision: timetable.revision ?? '—' }) }}</span>
    </header>

    <div v-if="!timetable.active" class="notice warning">
      {{ $t('rescheduling.noTimetable') }}
    </div>

    <div class="workspace-grid">
      <section class="panel absence-panel">
        <div class="panel-title">
          <div><span>1</span><h3>{{ $t('rescheduling.steps.absence') }}</h3></div>
        </div>
        <label>{{ $t('rescheduling.teacher') }}
          <select v-model.number="absence.professor_id" :disabled="!timetable.active">
            <option :value="null">{{ $t('common.selectOption') }}</option>
            <option v-for="teacher in teachers" :key="teacher.id" :value="teacher.id">{{ teacher.name }}</option>
          </select>
        </label>
        <label>{{ $t('rescheduling.date') }}<input v-model="absence.data" type="date" /></label>
        <div class="period-field">
          <span>{{ $t('rescheduling.absentPeriods') }}</span>
          <div class="periods">
            <label v-for="period in 9" :key="period" :class="{ selected: absence.periods.includes(period) }">
              <input v-model="absence.periods" type="checkbox" :value="period" />{{ $t('records.period', { period }) }}
            </label>
          </div>
        </div>
        <Button :label="$t('rescheduling.analyzeAll')" icon="pi pi-search" :loading="busy === 'analyze'" :disabled="!canAnalyze" @click="createAndAnalyze" />
      </section>

      <section class="panel recommendations-panel">
        <div class="panel-title">
          <div><span>2</span><h3>{{ $t('rescheduling.steps.recommendations') }}</h3></div>
          <div v-if="analysis" class="analysis-actions">
            <small>{{ $t('rescheduling.counts', { resolved: analysis.resolved_count, unresolved: analysis.unresolved_count }) }}</small>
            <Button :label="$t('rescheduling.cancelAbsence')" severity="danger" text size="small" @click="cancelAbsence" />
          </div>
        </div>
        <div v-if="!analysis" class="empty-state">{{ $t('rescheduling.analysisEmpty') }}</div>
        <div v-else-if="!analysis.tasks.length" class="notice success">{{ $t('rescheduling.noTasks') }}</div>
        <article v-for="task in analysis?.tasks || []" :key="task.target.occurrence_id" class="task-card">
          <div class="task-heading">
            <div><strong>{{ $t('records.period', { period: task.target.period }) }} · {{ task.target.class_code }} {{ task.target.subject }}</strong><small>{{ $t('rescheduling.originalTeacher', { teachers: joinItems(task.target.teacher_names) }) }}</small></div>
            <span :class="['status', task.status]">{{ task.status === 'recommended' ? $t('rescheduling.recommendable') : $t('rescheduling.unresolved') }}</span>
          </div>
          <template v-if="task.alternatives.length">
            <label>{{ $t('rescheduling.candidates') }}
              <select v-model="selectedCandidates[task.target.occurrence_id]">
                <option v-for="candidate in task.alternatives" :key="candidate.id" :value="candidate.id">
                  {{ kindLabel(candidate.kind) }} · {{ candidate.reason }}
                </option>
              </select>
            </label>
            <div class="movement-list" v-for="candidate in selectedForTask(task)" :key="candidate.id">
              <div v-for="(leg, index) in candidate.legs" :key="index">
                <span>{{ leg.class_code }} {{ leg.subject }}（{{ joinItems(leg.teacher_names) }}）</span>
                <b>{{ leg.from_date }} {{ $t('records.period', { period: leg.from_period }) }} → {{ leg.to_date }} {{ $t('records.period', { period: leg.to_period }) }}</b>
              </div>
            </div>
            <Button :label="$t('rescheduling.confirmArrangement')" icon="pi pi-check" severity="success" :loading="busy === task.target.occurrence_id" @click="confirmTask(task)" />
          </template>
          <p v-else class="unresolved-copy">{{ $t('rescheduling.noCandidate') }}</p>
        </article>
      </section>
    </div>

    <section class="panel effective-panel">
      <div class="panel-title">
        <div><span>3</span><h3>{{ $t('rescheduling.steps.effective') }}</h3></div>
        <label class="inline-date">{{ $t('rescheduling.date') }}<input v-model="effectiveDate" type="date" @change="loadEffective" /></label>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th v-if="isAdmin">{{ $t('rescheduling.manualSwap') }}</th><th>{{ $t('rescheduling.period') }}</th><th>{{ $t('rescheduling.class') }}</th><th>{{ $t('rescheduling.subject') }}</th><th>{{ $t('rescheduling.teacherColumn') }}</th><th>{{ $t('rescheduling.status') }}</th></tr></thead>
          <tbody>
            <tr v-for="lesson in effective.lessons || []" :key="lesson.occurrence_id">
              <td v-if="isAdmin"><input type="checkbox" :checked="manualSelected(lesson)" :disabled="lesson.locked || !lesson.lesson_id" @change="toggleManual(lesson)" /></td>
              <td>{{ $t('records.period', { period: lesson.period }) }}</td><td>{{ lesson.class_code }}</td><td>{{ lesson.subject }}</td>
              <td>{{ joinItems(lesson.teacher_names) }}</td>
              <td><span :class="['source-tag', lesson.source !== 'base' && 'changed']">{{ sourceLabel(lesson.source) }}</span></td>
            </tr>
            <tr v-if="!effective.lessons?.length"><td :colspan="isAdmin ? 6 : 5" class="empty-row">{{ $t('rescheduling.noLessons') }}</td></tr>
          </tbody>
        </table>
      </div>
      <div v-if="isAdmin && manualLessons.length" class="manual-box">
        <div><strong>{{ $t('rescheduling.manualSelected', { count: manualLessons.length }) }}</strong><small>{{ $t('rescheduling.manualHint') }}</small></div>
        <ol><li v-for="lesson in manualLessons" :key="lesson.occurrence_id">{{ lesson.date }} {{ $t('records.period', { period: lesson.period }) }} · {{ lesson.class_code }} {{ lesson.subject }}</li></ol>
        <input v-model="manualReason" :placeholder="$t('rescheduling.manualReason')" />
        <div class="manual-actions"><Button :label="$t('rescheduling.clear')" text @click="manualLessons = []" /><Button :label="$t('rescheduling.confirmManual')" icon="pi pi-check" :disabled="!manualCanSubmit" @click="submitManual" /></div>
      </div>
    </section>

    <div class="bottom-grid">
      <details class="panel history-panel" open>
        <summary>{{ $t('rescheduling.history') }}</summary>
        <div v-for="item in adjustments" :key="item.id" class="history-item">
          <div><strong>#{{ item.id }} · {{ kindLabel(item.kind) }}</strong><small>{{ formatTimestamp(item.confirmed_at) }} · {{ item.confirmed_by }}</small></div>
          <span :class="['status', item.status]">{{ item.status === 'confirmed' ? $t('rescheduling.confirmedLocked') : $t('records.statuses.reverted') }}</span>
          <Button v-if="isAdmin && item.status === 'confirmed'" :label="$t('rescheduling.revert')" severity="danger" text @click="revert(item.id)" />
        </div>
        <p v-if="!adjustments.length" class="muted">{{ $t('rescheduling.noHistory') }}</p>
      </details>

      <details v-if="isAdmin" class="panel closure-panel">
        <summary>{{ $t('rescheduling.closures') }}</summary>
        <p class="muted">{{ $t('rescheduling.closureHint') }}</p>
        <textarea v-model="closureText" rows="6" placeholder="2026-09-28&#10;2026-10-01"></textarea>
        <Button :label="$t('rescheduling.saveDates')" icon="pi pi-save" @click="saveClosures" />
      </details>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import axios from 'axios'
import Button from 'primevue/button'

const props = defineProps({ dataGlobal: Date, isAdmin: Boolean })
const { t, locale } = useI18n()
const joinItems = (items) => items.join(locale.value === 'en' ? ', ' : '、')
const iso = (value) => {
  const d = value || new Date()
  const local = new Date(d.getTime() - d.getTimezoneOffset() * 60000)
  return local.toISOString().slice(0, 10)
}
const formatTimestamp = (value) => value ? new Intl.DateTimeFormat(locale.value === 'en' ? 'en-HK' : 'zh-HK', {
  timeZone: 'Asia/Hong_Kong', year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', hour12: false
}).format(new Date(value)) : '—'

const busy = ref('')
const timetable = ref({ active: false })
const teachers = ref([])
const absence = reactive({ professor_id: null, data: iso(props.dataGlobal), periods: [] })
const currentAbsenceId = ref(null)
const analysis = ref(null)
const selectedCandidates = reactive({})
const effectiveDate = ref(iso(props.dataGlobal))
const effective = ref({ lessons: [] })
const adjustments = ref([])
const closureText = ref('')
const manualLessons = ref([])
const manualReason = ref('')

const canAnalyze = computed(() => timetable.value.active && absence.professor_id && absence.data && absence.periods.length)
const manualCanSubmit = computed(() => [2, 3].includes(manualLessons.value.length)
  && new Set(manualLessons.value.map(item => item.class_code)).size === 1 && manualReason.value.trim())
watch(() => props.dataGlobal, (value) => { absence.data = iso(value); effectiveDate.value = iso(value); loadEffective() })
watch(() => absence.data, () => loadDateContext())

const loadDateContext = async () => {
  if (!absence.data) {
    timetable.value = { active: false }
    teachers.value = []
    absence.professor_id = null
    return
  }
  const [timetableResponse, teacherResponse] = await Promise.all([
    axios.get('/api/timetables/current', { params: { data: absence.data } }),
    axios.get('/api/rescheduling/teachers', { params: { data: absence.data } })
  ])
  timetable.value = timetableResponse.data
  teachers.value = teacherResponse.data
  if (!teachers.value.some(teacher => teacher.id === absence.professor_id)) absence.professor_id = null
}

const loadBase = async () => {
  adjustments.value = (await axios.get('/api/adjustments')).data
  await loadDateContext()
  if (props.isAdmin) {
    const { data } = await axios.get('/api/calendar/closures')
    closureText.value = data.map(item => item.date).join('\n')
  }
}

const applyDefaults = () => {
  for (const task of analysis.value?.tasks || []) {
    selectedCandidates[task.target.occurrence_id] = task.recommended?.id || task.alternatives[0]?.id
  }
}

const createAndAnalyze = async () => {
  busy.value = 'analyze'
  try {
    const created = (await axios.post('/api/absence-cases', {
      professor_id: absence.professor_id, data: absence.data, periods: absence.periods.map(Number)
    })).data
    currentAbsenceId.value = created.id
    analysis.value = (await axios.post(`/api/absence-cases/${created.id}/analyze`)).data
    applyDefaults()
  } catch (error) {
    if (error.response?.status !== 409) throw error
    const cases = (await axios.get('/api/absence-cases', { params: { data: absence.data } })).data
    const existing = cases.find(item => item.professor_id === absence.professor_id && item.status !== 'cancelled')
    if (!existing) throw error
    currentAbsenceId.value = existing.id
    analysis.value = (await axios.post(`/api/absence-cases/${existing.id}/analyze`)).data
    applyDefaults()
  } finally { busy.value = '' }
}

const selectedForTask = (task) => task.alternatives.filter(item => item.id === selectedCandidates[task.target.occurrence_id])
const confirmTask = async (task) => {
  const candidateId = selectedCandidates[task.target.occurrence_id]
  if (!candidateId) return
  busy.value = task.target.occurrence_id
  try {
    await axios.post('/api/adjustments/confirm', {
      absence_case_id: currentAbsenceId.value, candidate_id: candidateId, expected_revision: analysis.value.revision
    })
    analysis.value = (await axios.post(`/api/absence-cases/${currentAbsenceId.value}/analyze`)).data
    applyDefaults(); await loadBase(); await loadEffective()
  } finally { busy.value = '' }
}

const loadEffective = async () => {
  if (!effectiveDate.value) return
  effective.value = (await axios.get('/api/effective-timetable', { params: { data: effectiveDate.value } })).data
}

const revert = async (id) => {
  await axios.post(`/api/adjustments/${id}/revert`)
  await loadBase(); await loadEffective()
  if (currentAbsenceId.value) {
    analysis.value = (await axios.post(`/api/absence-cases/${currentAbsenceId.value}/analyze`)).data
    applyDefaults()
  }
}

const cancelAbsence = async () => {
  if (!currentAbsenceId.value) return
  await axios.delete(`/api/absence-cases/${currentAbsenceId.value}`)
  currentAbsenceId.value = null
  analysis.value = null
  absence.periods = []
  await loadBase(); await loadEffective()
}

const saveClosures = async () => {
  const dates = [...new Set(closureText.value.split(/[\s,，]+/).map(value => value.trim()).filter(Boolean))]
  await axios.put('/api/calendar/closures', { closures: dates.map(data => ({ data })) })
  await loadBase()
}

const manualSelected = (lesson) => manualLessons.value.some(item => item.occurrence_id === lesson.occurrence_id)
const toggleManual = (lesson) => {
  const index = manualLessons.value.findIndex(item => item.occurrence_id === lesson.occurrence_id)
  if (index >= 0) manualLessons.value.splice(index, 1)
  else if (manualLessons.value.length < 3) manualLessons.value.push({ ...lesson, date: effectiveDate.value })
}
const submitManual = async () => {
  if (!manualCanSubmit.value) return
  const selected = manualLessons.value
  await axios.post('/api/adjustments/manual', {
    expected_revision: effective.value.revision,
    reason: manualReason.value.trim(),
    legs: selected.map((lesson, index) => {
      const destination = selected[(index + 1) % selected.length]
      return { occurrence_id: lesson.occurrence_id, from_date: lesson.date, to_date: destination.date, to_period: destination.period }
    })
  })
  manualLessons.value = []; manualReason.value = ''
  await loadBase(); await loadEffective()
}

const kindLabel = (kind) => t(`records.kinds.${kind}`, kind)
const sourceLabel = (source) => t(`rescheduling.sources.${source}`, source)

onMounted(async () => { await loadBase(); await loadEffective() })
</script>

<style scoped>
.rescheduling-page{display:flex;flex-direction:column;gap:1.25rem;color:#172033}.page-heading{display:flex;justify-content:space-between;gap:2rem;align-items:flex-start}.page-heading h2{font-size:2rem;margin:.15rem 0}.page-heading p{color:#657084}.eyebrow{color:#4965d6!important;font-weight:700;text-transform:uppercase;font-size:.78rem;letter-spacing:.08em}.revision{background:#eef2ff;color:#4256b5;padding:.5rem .75rem;border-radius:999px;font-size:.82rem;white-space:nowrap}.panel{background:#fff;border:1px solid #e4e8f0;border-radius:14px;padding:1.2rem;box-shadow:0 4px 18px rgba(35,45,75,.05)}details summary{font-weight:700;cursor:pointer;margin:-.2rem 0 .9rem}.workspace-grid{display:grid;grid-template-columns:minmax(280px,.72fr) minmax(460px,1.6fr);gap:1.25rem;align-items:start}.panel-title{display:flex;align-items:center;justify-content:space-between;margin-bottom:1rem}.panel-title>div{display:flex;align-items:center;gap:.55rem}.panel-title span{display:grid;place-items:center;width:1.8rem;height:1.8rem;border-radius:50%;background:#4965d6;color:#fff;font-weight:700}.panel-title h3{margin:0}.panel-title small{color:#657084}.analysis-actions{display:flex;align-items:center!important;gap:.4rem}.absence-panel,.absence-panel label{display:flex;flex-direction:column;gap:.8rem}.absence-panel label{gap:.3rem;font-weight:600;font-size:.88rem}select,input[type=date],input[type=file],textarea,.manual-box input{width:100%;border:1px solid #ccd3df;border-radius:8px;padding:.65rem;background:#fff;color:#172033}input[type=file]{padding:.48rem}.period-field>span{font-size:.88rem;font-weight:600}.periods{display:grid;grid-template-columns:repeat(3,1fr);gap:.45rem;margin-top:.35rem}.periods label{display:flex;flex-direction:row;align-items:center;justify-content:center;border:1px solid #dfe4ed;border-radius:8px;padding:.5rem!important;font-weight:500!important;cursor:pointer}.periods label.selected{border-color:#4965d6;background:#eef2ff;color:#344ba9}.periods input{width:auto}.import-grid{display:grid;grid-template-columns:1fr 1fr .7fr auto;align-items:end;gap:.8rem}.import-grid label{font-size:.82rem;font-weight:600}.preview-result{margin-top:1rem;padding:1rem;background:#f6f8fc;border-radius:10px}.preview-result ul{margin:.6rem 0 .8rem;padding-left:1.2rem;color:#8a5b16}.notice{padding:.85rem 1rem;border-radius:10px}.warning{background:#fff7e6;color:#8a5b16;border:1px solid #f0d69a}.success{background:#eaf8f0;color:#247147}.empty-state{display:grid;place-items:center;min-height:230px;text-align:center;color:#7b8597;border:1px dashed #d5dae4;border-radius:10px;padding:2rem}.task-card{border:1px solid #dfe4ed;border-radius:12px;padding:1rem;margin-bottom:.8rem}.task-heading{display:flex;justify-content:space-between;gap:1rem;margin-bottom:.8rem}.task-heading div{display:flex;flex-direction:column;gap:.22rem}.task-heading small{color:#657084}.status,.source-tag{font-size:.75rem;padding:.28rem .55rem;border-radius:999px;white-space:nowrap;background:#edf0f5;color:#5c6575}.status.recommended,.status.confirmed,.source-tag.changed{background:#e7f7ee;color:#237448}.status.unresolved{background:#fff0ed;color:#a84030}.movement-list{background:#f7f8fb;border-radius:9px;padding:.7rem;margin:.65rem 0}.movement-list div{display:flex;justify-content:space-between;gap:1rem;font-size:.82rem;padding:.28rem 0}.movement-list b{color:#4256b5;text-align:right}.unresolved-copy{color:#9b493d;margin:0}.effective-panel .inline-date{display:flex;align-items:center;gap:.5rem;font-size:.82rem}.effective-panel .inline-date input{width:auto}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;font-size:.88rem}th,td{text-align:left;padding:.7rem;border-bottom:1px solid #edf0f4}th{color:#657084;background:#fafbfc}.empty-row{text-align:center;color:#8490a3}.manual-box{margin-top:1rem;padding:1rem;border:1px solid #cfd8fa;background:#f7f8ff;border-radius:10px}.manual-box>div:first-child{display:flex;flex-direction:column}.manual-box small{color:#657084}.manual-box ol{margin:.65rem 0;padding-left:1.25rem}.manual-actions{display:flex;justify-content:flex-end;gap:.5rem;margin-top:.6rem}.bottom-grid{display:grid;grid-template-columns:1.5fr 1fr;gap:1.25rem}.history-item{display:grid;grid-template-columns:1fr auto auto;gap:.7rem;align-items:center;padding:.7rem 0;border-bottom:1px solid #edf0f4}.history-item div{display:flex;flex-direction:column}.history-item small,.muted{color:#758094;font-size:.82rem}.closure-panel textarea{margin:.6rem 0;resize:vertical}
@media(max-width:900px){.workspace-grid,.bottom-grid{grid-template-columns:1fr}.import-grid{grid-template-columns:1fr 1fr}.movement-list div{flex-direction:column;gap:.2rem}.movement-list b{text-align:left}}@media(max-width:600px){.page-heading{flex-direction:column;gap:.5rem}.import-grid{grid-template-columns:1fr}.periods{grid-template-columns:repeat(3,1fr)}.history-item{grid-template-columns:1fr auto}.history-item .p-button{grid-column:1/-1}.panel{padding:1rem}}
</style>
