<template>
  <section class="rescheduling-page">
    <header class="page-heading">
      <div>
        <h2>{{ $t('rescheduling.title') }}</h2>
        <p>{{ $t('rescheduling.description') }}</p>
      </div>
      <span class="revision">{{ $t('rescheduling.revision', { revision: timetable.revision ?? '-' }) }}</span>
    </header>

    <div v-if="!timetable.active" class="notice warning">
      {{ $t('rescheduling.noTimetable') }}
    </div>

    <div class="workspace-grid">
      <section class="panel absence-panel">
        <div class="panel-title">
          <div><span>1</span><h3>{{ $t('rescheduling.steps.absence') }}</h3></div>
        </div>
        <div class="teacher-field">
          <label for="absence-teachers">{{ $t('rescheduling.teachers') }}</label>
          <MultiSelect
            inputId="absence-teachers"
            v-model="absence.professor_ids"
            :options="teachers"
            optionLabel="name"
            optionValue="id"
            display="chip"
            filter
            :placeholder="dateContextLoading ? $t('rescheduling.checkingDate') : timetable.active ? $t('rescheduling.selectTeachers') : $t('rescheduling.invalidDate')"
            :disabled="dateContextLoading || !timetable.active"
          />
        </div>
        <label>{{ $t('rescheduling.absenceDate') }}<input v-model="absence.data" type="date" @change="loadDateContext()" /></label>
        <div class="period-field">
          <div class="period-heading">
            <span>{{ $t('rescheduling.absentPeriods') }}</span>
            <label class="all-day"><input v-model="allDay" type="checkbox" />{{ $t('rescheduling.allDay') }}</label>
          </div>
          <div class="periods">
            <label v-for="period in 9" :key="period" :class="{ selected: absence.periods.includes(period) }">
              <input v-model="absence.periods" type="checkbox" :value="period" />{{ $t('records.period', { period }) }}
            </label>
          </div>
        </div>
        <Button :label="$t('rescheduling.analyzeAll')" icon="pi pi-search" class="progress-fill-button" :class="{ 'is-progressing': busy === 'analyze' }" :loading="busy === 'analyze'" :disabled="!canAnalyze" @click="createAndAnalyze" />
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
        <article v-for="task in analysis?.tasks || []" :key="task.task_key" class="task-card">
          <div class="task-heading">
            <div><strong>{{ $t('records.period', { period: task.target.period }) }} · {{ task.target.class_code }} {{ task.target.subject }}</strong><small>{{ $t('rescheduling.originalTeacher', { teachers: joinItems(task.target.teacher_names) }) }}</small></div>
            <span :class="['status', task.status]">{{ task.status === 'recommended' ? $t('rescheduling.recommendable') : $t('rescheduling.unresolved') }}</span>
          </div>
          <template v-if="task.alternatives.length">
            <label>{{ $t('rescheduling.candidates') }}
              <select v-model="selectedCandidates[task.task_key]">
                <option v-for="candidate in task.alternatives" :key="candidate.id" :value="candidate.id">
                  {{ kindLabel(candidate.kind) }} · {{ candidate.reason }}{{ candidate.special_cross_day_moves ? ` · ${$t('rescheduling.specialCourseLater')}` : '' }}
                </option>
              </select>
            </label>
            <div class="movement-list" v-for="candidate in selectedForTask(task)" :key="candidate.id">
              <div v-for="(leg, index) in candidate.legs" :key="index">
                <span>{{ leg.class_code }} {{ leg.subject }}（{{ joinItems(leg.teacher_names) }}）</span>
                <b>{{ leg.from_date }} {{ $t('records.period', { period: leg.from_period }) }} → {{ leg.to_date }} {{ $t('records.period', { period: leg.to_period }) }}</b>
              </div>
            </div>
            <Button :label="$t('rescheduling.confirmArrangement')" icon="pi pi-check" severity="success" :loading="busy === task.task_key" @click="confirmTask(task)" />
          </template>
          <p v-else class="unresolved-copy">{{ $t('rescheduling.noCandidate') }}</p>
        </article>
      </section>
    </div>

    <section class="panel effective-panel">
      <div class="panel-title">
        <div>
          <span>3</span>
          <div class="title-copy"><h3>{{ $t('rescheduling.steps.effective') }}</h3><small>{{ $t('rescheduling.affectedHint') }}</small></div>
        </div>
        <div class="effective-filters">
          <label><input v-model="showAllLessons" type="checkbox" />{{ $t('rescheduling.showAllLessons') }}</label>
          <label class="inline-date">{{ $t('rescheduling.date') }}<input v-model="effectiveDate" type="date" @change="loadEffective" /></label>
        </div>
      </div>
      <div v-if="!showAllLessons">
        <div v-if="!affectedGroups.length" class="affected-empty">{{ $t('rescheduling.noAdjustments') }}</div>
        <template v-else>
          <div class="affected-view-bar">
            <div class="view-switch" role="group" :aria-label="$t('rescheduling.viewMode')">
              <button type="button" :class="{ active: affectedView === 'cards' }" @click="affectedView = 'cards'">{{ $t('rescheduling.cardView') }}</button>
              <button type="button" :class="{ active: affectedView === 'timetable' }" @click="affectedView = 'timetable'">{{ $t('rescheduling.timetableView') }}</button>
            </div>
            <div v-if="affectedView === 'timetable'" class="timetable-legend">
              <span><i class="moved-out"></i>{{ $t('rescheduling.movedOut') }}</span>
              <span><i class="moved-in"></i>{{ $t('rescheduling.movedIn') }}</span>
              <span><i class="covered"></i>{{ $t('rescheduling.covered') }}</span>
            </div>
          </div>
        <div v-if="affectedView === 'cards'" class="affected-grid">
          <article v-for="group in affectedGroups" :key="group.id" class="affected-card">
            <header>
              <div><strong>{{ joinItems(group.classes) }}</strong><span>{{ $t('rescheduling.affectedLessons', { count: group.lessons.length }) }}</span></div>
              <span class="source-tag changed">{{ sourceLabel(group.source) }}</span>
            </header>
            <div class="lesson-strip">
              <div v-for="lesson in group.lessons" :key="lesson.occurrence_id" class="lesson-change">
                <div v-if="lesson.source === 'emergency_cover'" class="cover-period">
                  <small>{{ $t('rescheduling.coverAt') }}</small><b>{{ $t('records.period', { period: lesson.period }) }}</b>
                </div>
                <div v-else class="period-flow">
                  <div><small>{{ $t('rescheduling.originalSlot') }}</small><b>{{ periodLabel(lesson.displayFromPeriod) }}</b></div>
                  <span aria-hidden="true">→</span>
                  <div><small>{{ $t('rescheduling.currentSlot') }}</small><b>{{ periodLabel(lesson.displayToPeriod) }}</b></div>
                  <em v-if="lesson.displayFromDate !== lesson.displayToDate">{{ lesson.displayFromDate }} → {{ lesson.displayToDate }}</em>
                </div>
                <div><strong>{{ lesson.class_code }} · {{ lesson.subject }}</strong><span>{{ joinItems(lesson.teacher_names) }}</span></div>
              </div>
            </div>
          </article>
        </div>
          <div v-else class="mini-timetable-wrap">
            <table class="mini-timetable">
              <thead><tr><th>{{ $t('rescheduling.class') }}</th><th v-for="period in 9" :key="period">{{ $t('records.period', { period }) }}</th></tr></thead>
              <tbody>
                <tr v-for="row in classTimetables" :key="row.classCode">
                  <th>{{ row.classCode }}</th>
                  <td v-for="slot in row.periods" :key="slot.period" :class="{ affected: slot.outgoing.length || slot.incoming.length }">
                    <div v-for="lesson in slot.outgoing" :key="`out-${lesson.occurrence_id}`" class="slot-change moved-out">
                      <small>{{ $t('rescheduling.movedOut') }}</small><strong>{{ lesson.subject }}</strong>
                    </div>
                    <div v-for="lesson in slot.incoming" :key="`in-${lesson.occurrence_id}`" :class="['slot-change', lesson.source === 'emergency_cover' ? 'covered' : 'moved-in']">
                      <small>{{ $t(lesson.source === 'emergency_cover' ? 'rescheduling.covered' : 'rescheduling.movedIn') }}</small><strong>{{ lesson.subject }}</strong><span>{{ joinItems(lesson.teacher_names) }}</span>
                    </div>
                    <div v-if="!slot.outgoing.length && !slot.incoming.length && slot.current.length" class="slot-current">
                      <template v-for="lesson in slot.current" :key="lesson.occurrence_id"><strong>{{ lesson.subject }}</strong><span>{{ joinItems(lesson.teacher_names) }}</span></template>
                    </div>
                    <span v-if="!slot.outgoing.length && !slot.incoming.length && !slot.current.length" class="slot-empty">—</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
      </div>
      <div v-else class="table-wrap">
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

  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import axios from 'axios'
import Button from 'primevue/button'
import MultiSelect from 'primevue/multiselect'

const props = defineProps({ dataGlobal: Date, isAdmin: Boolean })
const { t, locale } = useI18n()
const joinItems = (items) => items.join(locale.value === 'en' ? ', ' : '、')
const iso = (value) => {
  const d = value || new Date()
  const local = new Date(d.getTime() - d.getTimezoneOffset() * 60000)
  return local.toISOString().slice(0, 10)
}

const busy = ref('')
const dateContextLoading = ref(false)
const timetable = ref({ active: false })
const teachers = ref([])
const absence = reactive({ professor_ids: [], data: iso(props.dataGlobal), periods: [] })
const currentAbsenceIds = ref([])
const analysis = ref(null)
const selectedCandidates = reactive({})
const effectiveDate = ref(iso(props.dataGlobal))
const effective = ref({ lessons: [] })
const showAllLessons = ref(false)
const affectedView = ref('cards')
const manualLessons = ref([])
const manualReason = ref('')

const canAnalyze = computed(() => !dateContextLoading.value && timetable.value.active && absence.professor_ids.length && absence.data && absence.periods.length)
const affectedGroups = computed(() => {
  const groups = new Map()
  for (const lesson of effective.value.lessons?.filter(item => item.adjustment_id) || []) {
    if (!groups.has(lesson.adjustment_id)) groups.set(lesson.adjustment_id, { id: lesson.adjustment_id, source: lesson.source, classes: new Set(), lessons: [] })
    const group = groups.get(lesson.adjustment_id)
    group.classes.add(lesson.class_code)
    group.lessons.push(lesson)
  }
  return [...groups.values()].map(group => ({
    ...group,
    classes: [...group.classes],
    lessons: group.lessons.map((lesson, index, lessons) => ({
      ...lesson,
      displayFromPeriod: lesson.from_period ?? (group.source === 'direct_swap' && lessons.length === 2 ? lessons[1 - index].period : null),
      displayToPeriod: lesson.to_period ?? lesson.period,
      displayFromDate: lesson.from_date ?? effectiveDate.value,
      displayToDate: lesson.to_date ?? effectiveDate.value
    }))
  }))
})
const affectedLessons = computed(() => affectedGroups.value.flatMap(group => group.lessons))
const classTimetables = computed(() => [...new Set(affectedLessons.value.map(lesson => lesson.class_code))].sort().map(classCode => ({
  classCode,
  periods: Array.from({ length: 9 }, (_, index) => {
    const period = index + 1
    return {
      period,
      current: (effective.value.lessons || []).filter(lesson => lesson.lesson_id && lesson.class_code === classCode && lesson.period === period),
      outgoing: affectedLessons.value.filter(lesson => lesson.class_code === classCode && lesson.displayFromPeriod === period && (lesson.displayFromPeriod !== lesson.displayToPeriod || lesson.displayFromDate !== lesson.displayToDate)),
      incoming: affectedLessons.value.filter(lesson => lesson.class_code === classCode && lesson.displayToPeriod === period)
    }
  })
})))
const periodLabel = (period) => period ? t('records.period', { period }) : '—'
const allDay = computed({
  get: () => absence.periods.length === 9,
  set: (checked) => { absence.periods = checked ? Array.from({ length: 9 }, (_, index) => index + 1) : [] }
})
const manualCanSubmit = computed(() => [2, 3].includes(manualLessons.value.length)
  && new Set(manualLessons.value.map(item => item.class_code)).size === 1 && manualReason.value.trim())
watch(() => props.dataGlobal, (value) => {
  const nextDate = iso(value)
  const dateChanged = absence.data !== nextDate
  absence.data = nextDate
  effectiveDate.value = nextDate
  if (dateChanged) loadDateContext()
  loadEffective()
})

const loadDateContext = async (preferredTeacherIds = [...absence.professor_ids]) => {
  if (!absence.data) {
    timetable.value = { active: false }
    teachers.value = []
    absence.professor_ids = []
    return
  }
  const requestedDate = absence.data
  dateContextLoading.value = true
  timetable.value = { active: false }
  teachers.value = []
  absence.professor_ids = []
  try {
    const [timetableResponse, teacherResponse] = await Promise.all([
      axios.get('/api/timetables/current', { params: { data: requestedDate } }),
      axios.get('/api/rescheduling/teachers', { params: { data: requestedDate } })
    ])
    if (absence.data !== requestedDate) return
    timetable.value = timetableResponse.data
    teachers.value = teacherResponse.data
    const availableIds = new Set(teachers.value.map(teacher => teacher.id))
    absence.professor_ids = preferredTeacherIds.filter(id => availableIds.has(id))
  } finally {
    if (absence.data === requestedDate) dateContextLoading.value = false
  }
}

const applyDefaults = () => {
  for (const key of Object.keys(selectedCandidates)) delete selectedCandidates[key]
  for (const task of analysis.value?.tasks || []) {
    selectedCandidates[task.task_key] = task.recommended?.id || task.alternatives[0]?.id
  }
}

const createAndAnalyze = async () => {
  busy.value = 'analyze'
  try {
    const created = (await axios.post('/api/absence-cases/batch', {
      professor_ids: absence.professor_ids, data: absence.data, periods: absence.periods.map(Number)
    })).data
    currentAbsenceIds.value = created.batch_absence_case_ids
    analysis.value = created
    applyDefaults()
  } finally { busy.value = '' }
}

const selectedForTask = (task) => task.alternatives.filter(item => item.id === selectedCandidates[task.task_key])
const confirmTask = async (task) => {
  const candidateId = selectedCandidates[task.task_key]
  if (!candidateId) return
  busy.value = task.task_key
  try {
    const response = (await axios.post('/api/adjustments/confirm', {
      absence_case_id: task.absence_case_id, candidate_id: candidateId, expected_revision: analysis.value.revision
    })).data
    analysis.value = response.analysis
    applyDefaults(); await loadDateContext(); await loadEffective()
  } finally { busy.value = '' }
}

const loadEffective = async () => {
  if (!effectiveDate.value) return
  effective.value = (await axios.get('/api/effective-timetable', { params: { data: effectiveDate.value } })).data
}

const cancelAbsence = async () => {
  if (!currentAbsenceIds.value.length) return
  await axios.post('/api/absence-cases/cancel-batch', { absence_case_ids: currentAbsenceIds.value })
  currentAbsenceIds.value = []
  analysis.value = null
  absence.periods = []
  await loadDateContext(); await loadEffective()
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
  await loadDateContext(); await loadEffective()
}

const kindLabel = (kind) => t(`records.kinds.${kind}`, kind)
const sourceLabel = (source) => t(`rescheduling.sources.${source}`, source)

const resumeAbsence = async (record) => {
  busy.value = 'analyze'
  currentAbsenceIds.value = [record.entity_id]
  absence.data = record.date
  absence.periods = [...record.periods]
  effectiveDate.value = record.date
  analysis.value = null
  try {
    await loadDateContext([record.professor_id])
    if (!timetable.value.active || !absence.professor_ids.length) return
    analysis.value = (await axios.post(`/api/absence-cases/${record.entity_id}/analyze`)).data
    applyDefaults()
    await loadEffective()
  } finally { busy.value = '' }
}

defineExpose({ resumeAbsence })

onMounted(async () => { await loadDateContext(); await loadEffective() })
</script>

<style scoped>
.rescheduling-page { display: grid; gap: 1.25rem; color: var(--text-color-primary); }
.page-heading { display: flex; justify-content: space-between; gap: 2rem; align-items: flex-start; padding-bottom: .25rem; }
.page-heading h2 { margin: 0 0 .35rem; font-size: clamp(1.65rem, 3vw, 2.15rem); line-height: 1.15; letter-spacing: -.035em; }
.page-heading p { max-width: 65ch; color: var(--text-color-secondary); }
.revision { padding-top: .4rem; color: var(--text-color-secondary); font-size: .8rem; white-space: nowrap; }
.panel { min-width: 0; background: var(--card-background); border: 1px solid var(--border-color); border-radius: 12px; padding: 1.25rem; }
.workspace-grid { display: grid; grid-template-columns: minmax(300px, .78fr) minmax(460px, 1.45fr); gap: 1.25rem; align-items: start; }
.panel-title { display: flex; align-items: center; justify-content: space-between; gap: 1rem; margin-bottom: 1rem; }
.panel-title > div { display: flex; align-items: center; gap: .65rem; }
.panel-title > div:first-child > span { display: grid; place-items: center; width: 1.75rem; height: 1.75rem; border-radius: 7px; background: var(--primary-color-light); color: var(--primary-color-dark); font-size: .8rem; font-weight: 750; }
.panel-title h3 { margin: 0; font-size: 1rem; }
.panel-title small { color: var(--text-color-secondary); }
.title-copy { display: flex; flex-direction: column; gap: .12rem; }
.analysis-actions { display: flex; align-items: center !important; gap: .45rem; }
.absence-panel, .absence-panel label { display: flex; flex-direction: column; gap: .8rem; }
.teacher-field { display: flex; flex-direction: column; gap: .35rem; }
.absence-panel label { gap: .35rem; color: #344054; font-size: .84rem; font-weight: 650; }
.absence-panel :deep(.p-multiselect) { width: 100%; min-height: 2.55rem; border-color: #cfd6df; }
.absence-panel :deep(.p-multiselect-label) { padding: .6rem .7rem; }
select, input[type=date], input[type=file], textarea, .manual-box input { width: 100%; min-height: 2.55rem; border: 1px solid #cfd6df; border-radius: 8px; padding: .6rem .7rem; background: #fff; color: var(--text-color-primary); }
select:hover, input:hover, textarea:hover { border-color: #aeb8c5; }
select:focus, input:focus, textarea:focus { border-color: var(--primary-color); }
input[type=checkbox] { accent-color: var(--primary-color); }
input[type=file] { padding: .45rem; }
.period-heading { display: flex; align-items: center; justify-content: space-between; gap: .75rem; font-size: .84rem; font-weight: 650; }
.absence-panel .all-day { flex-direction: row; align-items: center; gap: .35rem; font-weight: 600; cursor: pointer; }
.all-day input { width: auto; min-height: auto; }
.periods { display: grid; grid-template-columns: repeat(3, 1fr); gap: .45rem; margin-top: .4rem; }
.periods label { display: flex; flex-direction: row; align-items: center; justify-content: center; border: 1px solid var(--border-color); border-radius: 8px; padding: .55rem !important; font-weight: 550 !important; cursor: pointer; }
.periods label:hover { border-color: #aeb8c5; background: var(--surface-soft); }
.periods label.selected { border-color: #93b4f7; background: var(--highlight-bg); color: var(--primary-color-dark); }
.periods input { width: auto; min-height: auto; }
.notice { padding: .8rem 1rem; border-radius: 8px; border-left: 3px solid currentColor; }
.warning { background: #fff8e8; color: #8a5b16; }
.success { background: #ebf8ef; color: #247147; }
.empty-state { display: grid; place-items: center; min-height: 230px; padding: 2rem; border-radius: 10px; background: var(--surface-soft); color: var(--text-color-secondary); text-align: center; }
.task-card { margin-bottom: .8rem; padding: 1rem; border: 1px solid var(--border-color); border-left: 3px solid #93b4f7; border-radius: 10px; }
.task-card:last-child { margin-bottom: 0; }
.task-heading { display: flex; justify-content: space-between; gap: 1rem; margin-bottom: .8rem; }
.task-heading div { display: flex; flex-direction: column; gap: .2rem; }
.task-heading small { color: var(--text-color-secondary); }
.status, .source-tag { display: inline-flex; align-items: center; width: fit-content; padding: .24rem .52rem; border-radius: 999px; background: #eef1f4; color: #596476; font-size: .74rem; white-space: nowrap; }
.status.recommended, .status.confirmed, .source-tag.changed { background: #e4f5e9; color: #216a42; }
.status.unresolved { background: #fdecea; color: #9b3b30; }
.movement-list { margin: .7rem 0; padding: .7rem .8rem; border-radius: 8px; background: var(--surface-soft); }
.movement-list div { display: flex; justify-content: space-between; gap: 1rem; padding: .3rem 0; font-size: .82rem; }
.movement-list b { color: var(--primary-color-dark); text-align: right; }
.unresolved-copy { margin: 0; color: #9b493d; }
.effective-filters { display: flex; align-items: center; gap: 1rem; }
.effective-filters > label:first-child { display: flex; align-items: center; gap: .35rem; color: var(--text-color-secondary); font-size: .82rem; white-space: nowrap; }
.effective-panel .inline-date { display: flex; align-items: center; gap: .55rem; color: var(--text-color-secondary); font-size: .82rem; }
.effective-panel .inline-date input { width: auto; }
.affected-view-bar { display: flex; align-items: center; justify-content: space-between; gap: 1rem; margin-bottom: .75rem; }
.view-switch { display: inline-flex; padding: .2rem; border-radius: 8px; background: var(--surface-soft); }
.view-switch button { padding: .42rem .7rem; border: 0; border-radius: 6px; background: transparent; color: var(--text-color-secondary); cursor: pointer; font-size: .78rem; font-weight: 650; transition: background .15s ease, color .15s ease; }
.view-switch button:hover { color: var(--text-color-primary); }
.view-switch button.active { background: #fff; color: var(--primary-color-dark); box-shadow: 0 1px 3px rgba(28, 45, 78, .12); }
.view-switch button:focus-visible { box-shadow: var(--focus-ring); }
.timetable-legend { display: flex; flex-wrap: wrap; gap: .8rem; color: var(--text-color-secondary); font-size: .72rem; }
.timetable-legend span { display: flex; align-items: center; gap: .3rem; }
.timetable-legend i { width: .65rem; height: .65rem; border-radius: 2px; }
.timetable-legend .moved-out { background: #fbe5e2; }
.timetable-legend .moved-in { background: #def1e5; }
.timetable-legend .covered { background: #fff0c7; }
.affected-grid { display: grid; gap: .75rem; }
.affected-card { padding: 1rem; border: 1px solid var(--border-color); border-left: 3px solid #70a086; border-radius: 10px; background: #fff; }
.affected-card header { display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; margin-bottom: .8rem; }
.affected-card header > div { display: flex; flex-direction: column; gap: .1rem; }
.affected-card header strong { font-size: 1rem; }
.affected-card header span:not(.source-tag) { color: var(--text-color-secondary); font-size: .78rem; }
.lesson-strip { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: .55rem; }
.lesson-change { display: grid; grid-template-columns: auto minmax(0, 1fr); align-items: center; gap: .8rem; min-width: 0; padding: .75rem; border-radius: 8px; background: var(--surface-soft); }
.period-flow { position: relative; display: flex; align-items: center; gap: .35rem; padding-bottom: .05rem; }
.period-flow > div, .cover-period { display: flex; flex-direction: column; gap: .05rem; }
.period-flow small, .cover-period small { color: var(--text-color-secondary); font-size: .64rem; }
.period-flow b, .cover-period b { color: #216a42; font-size: .8rem; font-variant-numeric: tabular-nums; white-space: nowrap; }
.period-flow > span { color: #70a086; font-weight: 750; }
.period-flow em { position: absolute; top: 100%; left: 0; color: var(--text-color-secondary); font-size: .62rem; font-style: normal; white-space: nowrap; }
.lesson-change > div:last-child { display: flex; min-width: 0; flex-direction: column; gap: .08rem; }
.lesson-change strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: .86rem; }
.lesson-change div span { overflow: hidden; color: var(--text-color-secondary); font-size: .78rem; text-overflow: ellipsis; white-space: nowrap; }
.affected-empty { display: grid; min-height: 110px; place-items: center; border-radius: 10px; background: var(--surface-soft); color: var(--text-color-secondary); text-align: center; }
.mini-timetable-wrap { overflow-x: auto; border: 1px solid var(--border-color); border-radius: 10px; }
.mini-timetable { min-width: 1040px; table-layout: fixed; font-size: .75rem; }
.mini-timetable th, .mini-timetable td { width: 108px; padding: .45rem; vertical-align: top; }
.mini-timetable thead th { text-align: center; }
.mini-timetable th:first-child { position: sticky; left: 0; z-index: 1; width: 72px; background: #fff; color: var(--text-color-primary); font-size: .86rem; }
.mini-timetable thead th:first-child { z-index: 2; background: var(--surface-soft); }
.mini-timetable td { height: 74px; background: #fff; }
.mini-timetable td.affected { background: #fbfcfe; }
.slot-change, .slot-current { display: flex; min-width: 0; flex-direction: column; gap: .05rem; padding: .3rem .38rem; border-radius: 5px; }
.slot-change + .slot-change { margin-top: .25rem; }
.slot-change small { font-size: .62rem; font-weight: 650; }
.slot-change strong, .slot-current strong { overflow: hidden; font-size: .72rem; text-overflow: ellipsis; white-space: nowrap; }
.slot-change span, .slot-current span { overflow: hidden; color: var(--text-color-secondary); font-size: .62rem; text-overflow: ellipsis; white-space: nowrap; }
.slot-change.moved-out { background: #fbe5e2; color: #8e3f37; }
.slot-change.moved-in { background: #def1e5; color: #216a42; }
.slot-change.covered { background: #fff0c7; color: #805c12; }
.slot-current { color: #596476; }
.slot-empty { display: block; padding-top: .65rem; color: #b5bdc8; text-align: center; }
.table-wrap { overflow: auto; border: 1px solid var(--border-color); border-radius: 10px; }
table { width: 100%; min-width: 640px; border-collapse: collapse; font-size: .86rem; }
th, td { padding: .72rem .75rem; border-bottom: 1px solid #edf0f3; text-align: left; }
th { background: var(--surface-soft); color: var(--text-color-secondary); font-size: .78rem; font-weight: 700; white-space: nowrap; }
tbody tr:last-child td { border-bottom: 0; }
tbody tr:hover { background: #fbfcfe; }
.empty-row { text-align: center; color: var(--text-color-secondary); }
.manual-box { margin-top: 1rem; padding: 1rem; border: 1px solid #b9cdf8; border-radius: 10px; background: var(--highlight-bg); }
.manual-box > div:first-child { display: flex; flex-direction: column; }
.manual-box small { color: var(--text-color-secondary); }
.manual-box ol { margin: .65rem 0; padding-left: 1.25rem; }
.manual-actions { display: flex; justify-content: flex-end; gap: .5rem; margin-top: .6rem; }
@media (max-width: 900px) {
  .workspace-grid { grid-template-columns: 1fr; }
  .movement-list div { flex-direction: column; gap: .2rem; }
  .movement-list b { text-align: left; }
}

@media (max-width: 600px) {
  .page-heading { flex-direction: column; gap: .35rem; }
  .revision { padding-top: 0; }
  .panel-title { align-items: flex-start; }
  .effective-panel .panel-title { flex-direction: column; }
  .effective-filters { width: 100%; align-items: flex-start; flex-direction: column-reverse; }
  .affected-view-bar { align-items: flex-start; flex-direction: column; }
  .analysis-actions { align-items: flex-end !important; flex-direction: column; }
  .task-heading { flex-direction: column; }
  .panel { padding: 1rem; }
}
</style>
