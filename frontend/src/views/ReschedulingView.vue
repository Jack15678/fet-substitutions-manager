<template>
  <section class="rescheduling-page">
    <header class="page-heading">
      <div>
        <h2>{{ $t('rescheduling.title') }}</h2>
      </div>
      <div class="page-actions">
        <span class="revision">{{ $t('rescheduling.revision', { revision: timetable.revision ?? '-' }) }}</span>
        <Button :label="$t('rescheduling.addAbsence')" @click="openAbsencePanel" />
      </div>
    </header>

    <section class="panel recommendations-panel">
      <div class="panel-title">
        <div><h3>{{ $t('rescheduling.steps.recommendations') }}</h3></div>
        <div v-if="analysis" class="analysis-actions">
          <small>{{ $t('rescheduling.counts', { resolved: analysis.resolved_count, unresolved: analysis.unresolved_count }) }}</small>
          <Button v-if="currentAbsenceIds.length" :label="$t('rescheduling.cancelAbsence')" severity="danger" text size="small" @click="cancelAbsence" />
        </div>
      </div>
      <div v-if="batchAnalyses.length > 1" class="analysis-dates" role="tablist" :aria-label="$t('rescheduling.analysisDates')">
        <button
          v-for="item in batchAnalyses"
          :key="item.date"
          type="button"
          role="tab"
          :aria-selected="selectedAnalysisDate === item.date"
          :class="{ active: selectedAnalysisDate === item.date }"
          :disabled="analysisSwitchLoading"
          @click="selectAnalysisDate(item.date)"
        >{{ dateLabel(item.date) }}</button>
      </div>
      <div v-if="!analysis" class="empty-state">
        <p>{{ $t('rescheduling.analysisEmpty') }}</p>
        <Button :label="$t('rescheduling.addAbsence')" outlined @click="openAbsencePanel" />
      </div>
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
          <div class="candidate-actions">
            <Button :label="$t('rescheduling.verifyTimetables')" severity="secondary" outlined :loading="verificationLoading" @click="verifyTask(task)" />
            <Button :label="$t('rescheduling.confirmArrangement')" severity="success" :loading="busy === task.task_key" @click="confirmTask(task)" />
          </div>
        </template>
        <p v-else class="unresolved-copy">{{ $t('rescheduling.noCandidate') }}</p>
      </article>
    </section>

    <Sidebar v-model:visible="absencePanelVisible" position="right" :modal="true" :style="{ width: 'min(100vw, 680px)' }" class="absence-sidebar">
      <template #header>
        <div class="absence-sidebar-title">
          <h3>{{ $t('rescheduling.addAbsence') }}</h3>
          <p>{{ $t('rescheduling.addAbsenceHint') }}</p>
        </div>
      </template>
      <form class="absence-form" @submit.prevent="createAndAnalyze">
        <section v-for="entry in absenceEntries" :key="entry.id" class="absence-entry">
          <header>
            <strong>{{ entryTeacherName(entry) || $t('rescheduling.newAbsenceRecord') }}</strong>
            <Button v-if="absenceEntries.length > 1" type="button" :label="$t('common.delete')" severity="danger" text size="small" @click="removeAbsenceEntry(entry.id)" />
          </header>
          <div class="absence-entry-grid">
            <label>{{ $t('rescheduling.teacher') }}
              <select v-model.number="entry.professor_id" :disabled="entry.loading || !entry.active" required>
                <option :value="null">{{ entry.loading ? $t('rescheduling.checkingDate') : entry.active ? $t('rescheduling.selectTeacher') : $t('rescheduling.invalidDate') }}</option>
                <option v-for="teacher in entry.teachers" :key="teacher.id" :value="teacher.id">{{ teacher.name }}</option>
              </select>
            </label>
            <label>{{ $t('rescheduling.absenceDate') }}
              <input v-model="entry.data" type="date" required @change="loadAbsenceEntryContext(entry)" />
            </label>
          </div>
          <p v-if="!entry.loading && entry.data && !entry.active" class="entry-error">{{ $t('rescheduling.invalidDate') }}</p>
          <div class="period-field">
            <div class="period-heading">
              <span>{{ $t('rescheduling.absentPeriods') }}</span>
              <label class="all-day"><input type="checkbox" :checked="entryAllDay(entry)" @change="setEntryAllDay(entry, $event.target.checked)" />{{ $t('rescheduling.allDay') }}</label>
            </div>
            <div class="periods">
              <label v-for="period in 9" :key="period" :class="{ selected: entry.periods.includes(period) }">
                <input v-model="entry.periods" type="checkbox" :value="period" />{{ $t('records.period', { period }) }}
              </label>
            </div>
          </div>
        </section>

        <div class="add-entry-row">
          <Button type="button" :label="$t('rescheduling.addAnotherTeacher')" text :disabled="absenceEntries.length >= 3" @click="addAbsenceEntry" />
          <small>{{ $t('rescheduling.absenceLimit', { count: absenceEntries.length }) }}</small>
        </div>
        <p v-if="absenceError" class="absence-form-error" role="alert">{{ absenceError }}</p>
        <footer class="absence-form-actions">
          <Button :label="$t('common.cancel')" text type="button" @click="absencePanelVisible = false" />
          <Button type="submit" :label="$t('rescheduling.createAndAnalyze')" class="progress-fill-button" :class="{ 'is-progressing': busy === 'analyze' }" :loading="busy === 'analyze'" :disabled="!canAnalyze" />
        </footer>
      </form>
    </Sidebar>

    <Dialog v-model:visible="verificationVisible" modal :header="$t('rescheduling.verifyTitle')" :style="{ width: 'min(96vw, 1120px)' }">
      <div v-if="verificationLoading" class="verification-loading">{{ $t('common.loading') }}</div>
      <div v-else class="verification-content">
        <p>{{ $t('rescheduling.verifyHint') }}</p>
        <section v-for="teacher in verificationTimetables" :key="teacher.id" class="verification-teacher">
          <h4>{{ teacher.name }}</h4>
          <div class="verification-wrap">
            <table class="verification-timetable">
              <thead><tr><th>{{ $t('rescheduling.date') }}</th><th v-for="period in 9" :key="period">{{ $t('records.period', { period }) }}</th></tr></thead>
              <tbody>
                <tr v-for="day in teacher.days" :key="day.date">
                  <th>{{ dateLabel(day.date) }}</th>
                  <td v-for="slot in day.slots" :key="slot.period">
                    <div v-for="lesson in slot.lessons" :key="lesson.key" :class="['verification-lesson', { adjusted: lesson.adjusted }]">
                      <small v-if="lesson.adjusted">{{ $t('rescheduling.adjusted') }}</small>
                      <strong>{{ lesson.class_code }}</strong><span>{{ lesson.subject }}</span>
                    </div>
                    <span v-if="!slot.lessons.length" class="slot-empty">—</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </Dialog>

    <section class="panel effective-panel">
      <div class="panel-title">
        <div>
          <div class="title-copy"><h3>{{ $t('rescheduling.steps.effective') }}</h3><small>{{ $t('rescheduling.affectedHint') }}</small></div>
        </div>
        <div class="effective-filters">
          <label class="inline-date">{{ $t('rescheduling.date') }}<input v-model="effectiveDate" type="date" @change="loadEffective" /></label>
        </div>
      </div>
      <div>
        <div v-if="!affectedGroups.length" class="affected-empty">{{ $t('rescheduling.noAdjustments') }}</div>
        <template v-else>
          <div class="affected-view-bar">
            <div class="view-switch" role="group" :aria-label="$t('rescheduling.viewMode')">
              <button type="button" :class="{ active: affectedView === 'timetable' }" @click="affectedView = 'timetable'">{{ $t('rescheduling.timetableView') }}</button>
              <button type="button" :class="{ active: affectedView === 'cards' }" @click="affectedView = 'cards'">{{ $t('rescheduling.cardView') }}</button>
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
              <div class="affected-card-title">
                <strong>{{ joinItems(group.classes) }}</strong>
                <span>{{ $t('rescheduling.affectedLessons', { count: group.legs.length }) }}</span>
                <span class="source-tag changed">{{ sourceLabel(group.source) }}</span>
              </div>
              <div v-if="group.source !== 'emergency_cover'" class="cycle-route" :aria-label="$t('rescheduling.cycleClosed', { number: 1 })">
                <template v-for="(_, index) in group.legs" :key="`route-${group.id}-${index}`">
                  <span class="cycle-route-step">{{ index + 1 }}</span><span class="cycle-route-arrow" aria-hidden="true">→</span>
                </template>
                <span class="cycle-route-step">1</span>
              </div>
            </header>
            <div v-if="group.source === 'emergency_cover'" class="cover-link">
              <div><small>{{ $t('rescheduling.coverAt') }}</small><b>{{ group.legs[0].from_date }} · {{ periodLabel(group.legs[0].from_period) }}</b></div>
              <span aria-hidden="true">→</span>
              <div><strong>{{ group.legs[0].class_code }} · {{ group.legs[0].subject }}</strong><span>{{ group.legs[0].replacement_teacher_name }}</span></div>
            </div>
            <div v-else class="cycle-table-wrap">
              <table class="cycle-table" :aria-label="$t('rescheduling.cardView')">
                <thead><tr>
                  <th class="cycle-order">#</th>
                  <th>{{ $t('rescheduling.class') }} · {{ $t('rescheduling.subject') }}</th>
                  <th>{{ $t('rescheduling.teacherColumn') }}</th>
                  <th>{{ $t('rescheduling.originalSlot') }}</th>
                  <th class="cycle-table-arrow" aria-hidden="true"></th>
                  <th>{{ $t('rescheduling.currentSlot') }}</th>
                </tr></thead>
                <tbody>
                  <tr v-for="(leg, index) in group.legs" :key="`${group.id}-${index}`">
                    <td class="cycle-order"><span>{{ index + 1 }}</span></td>
                    <td><strong>{{ leg.class_code }} · {{ leg.subject }}</strong></td>
                    <td class="cycle-teacher">{{ joinItems(leg.teacher_names) }}</td>
                    <td class="cycle-time">{{ leg.from_date }} · {{ periodLabel(leg.from_period) }}</td>
                    <td class="cycle-table-arrow" aria-hidden="true">→</td>
                    <td class="cycle-time">{{ leg.to_date }} · {{ periodLabel(leg.to_period) }}</td>
                  </tr>
                </tbody>
              </table>
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
                      <small>{{ $t('rescheduling.movedOut') }}</small><strong>{{ lesson.subject }}</strong><span>{{ joinItems(lesson.teacher_names) }}</span>
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
    </section>

    <section v-if="isAdmin" class="panel leave-panel">
      <div class="leave-heading">
        <div><h3>{{ $t('leave.title') }}</h3><p>{{ $t('leave.description') }}</p></div>
        <Button v-if="editingLeaveId" :label="$t('leave.cancelEdit')" text @click="resetLeave" />
      </div>
      <form class="leave-form" @submit.prevent="saveLeave">
        <label>{{ $t('leave.teacher') }}
          <select v-model.number="leave.professor_id" required>
            <option :value="null">{{ $t('common.selectOption') }}</option>
            <option v-for="teacher in leaveTeachers" :key="teacher.id" :value="teacher.id">{{ teacher.name }}</option>
          </select>
        </label>
        <label>{{ $t('leave.type') }}
          <select v-model="leave.leave_type" required>
            <option value="sick">{{ $t('leave.types.sick') }}</option>
            <option value="maternity">{{ $t('leave.types.maternity') }}</option>
            <option value="other">{{ $t('leave.types.other') }}</option>
          </select>
        </label>
        <label>{{ $t('leave.startDate') }}<input v-model="leave.start_date" type="date" required /></label>
        <label>{{ $t('leave.endDate') }}<input v-model="leave.end_date" type="date" required /></label>
        <Button type="submit" :label="editingLeaveId ? $t('leave.update') : $t('leave.add')" :loading="leaveBusy" />
      </form>
      <div v-if="leaves.length" class="leave-list">
        <article v-for="item in leaves" :key="item.id">
          <div><strong>{{ item.teacher_name }}</strong><span>{{ leaveTypeLabel(item.leave_type) }} · {{ item.start_date }} → {{ item.end_date }}</span></div>
          <div><Button :label="$t('common.edit')" text @click="editLeave(item)" /><Button :label="$t('common.delete')" severity="danger" text @click="removeLeave(item.id)" /></div>
        </article>
      </div>
      <p v-else class="empty-state compact">{{ $t('leave.empty') }}</p>
    </section>

  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import axios from 'axios'
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import Sidebar from 'primevue/sidebar'

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
let absenceEntryId = 0
const newAbsenceEntry = () => ({
  id: ++absenceEntryId,
  professor_id: null,
  data: iso(props.dataGlobal),
  periods: [],
  teachers: [],
  active: false,
  loading: false,
})
const absencePanelVisible = ref(false)
const absenceEntries = ref([])
const absenceError = ref('')
const currentAbsenceIds = ref([])
const analysis = ref(null)
const batchAnalyses = ref([])
const selectedAnalysisDate = ref('')
const analysisSwitchLoading = ref(false)
const selectedCandidates = reactive({})
const effectiveDate = ref(iso(props.dataGlobal))
const effective = ref({ lessons: [] })
const affectedView = ref('timetable')
const verificationVisible = ref(false)
const verificationLoading = ref(false)
const verificationTimetables = ref([])
const leaves = ref([])
const leaveTeachers = ref([])
const leaveBusy = ref(false)
const editingLeaveId = ref(null)
const leave = reactive({ professor_id: null, leave_type: 'sick', start_date: '', end_date: '' })

const canAnalyze = computed(() => absenceEntries.value.length > 0 && absenceEntries.value.every(entry => (
  !entry.loading && entry.active && entry.professor_id && entry.data && entry.periods.length
)))
const affectedGroups = computed(() => (effective.value.adjustments || []).map(adjustment => ({
  id: adjustment.id,
  source: adjustment.kind,
  classes: [...new Set(adjustment.legs.map(leg => leg.class_code))],
  legs: adjustment.legs
})))
const affectedLessons = computed(() => affectedGroups.value.flatMap(group => group.legs
  .filter(leg => leg.from_date === effectiveDate.value || leg.to_date === effectiveDate.value)
  .map((leg, index) => ({
    ...leg,
    occurrence_id: `adjustment-${group.id}-${index}`,
    source: group.source,
    teacher_names: group.source === 'emergency_cover' && leg.replacement_teacher_name
      ? [leg.replacement_teacher_name]
      : leg.teacher_names,
    displayFromPeriod: leg.from_period,
    displayToPeriod: leg.to_period,
    displayFromDate: leg.from_date,
    displayToDate: leg.to_date
  }))))
const classTimetables = computed(() => [...new Set(affectedLessons.value.map(lesson => lesson.class_code))].sort().map(classCode => ({
  classCode,
  periods: Array.from({ length: 9 }, (_, index) => {
    const period = index + 1
    return {
      period,
      current: (effective.value.lessons || []).filter(lesson => lesson.lesson_id && lesson.class_code === classCode && lesson.period === period),
      outgoing: affectedLessons.value.filter(lesson => lesson.class_code === classCode && lesson.displayFromDate === effectiveDate.value && lesson.displayFromPeriod === period && (lesson.displayFromPeriod !== lesson.displayToPeriod || lesson.displayFromDate !== lesson.displayToDate)),
      incoming: affectedLessons.value.filter(lesson => lesson.class_code === classCode && lesson.displayToDate === effectiveDate.value && lesson.displayToPeriod === period)
    }
  })
})))
const periodLabel = (period) => period ? t('records.period', { period }) : '—'
watch(() => props.dataGlobal, (value) => {
  const nextDate = iso(value)
  effectiveDate.value = nextDate
  loadDateContext()
  loadEffective()
})

const loadDateContext = async () => {
  const requestedDate = iso(props.dataGlobal)
  if (!requestedDate) {
    timetable.value = { active: false }
    return
  }
  dateContextLoading.value = true
  timetable.value = { active: false }
  try {
    const timetableResponse = await axios.get('/api/timetables/current', { params: { data: requestedDate } })
    if (iso(props.dataGlobal) !== requestedDate) return
    timetable.value = timetableResponse.data
  } finally {
    if (iso(props.dataGlobal) === requestedDate) dateContextLoading.value = false
  }
}

const loadAbsenceEntryContext = async (entry) => {
  const requestedDate = entry.data
  entry.loading = true
  entry.active = false
  entry.teachers = []
  try {
    const [timetableResponse, teacherResponse] = await Promise.all([
      axios.get('/api/timetables/current', { params: { data: requestedDate }, _silent: true }),
      axios.get('/api/rescheduling/teachers', { params: { data: requestedDate }, _silent: true }),
    ])
    if (entry.data !== requestedDate) return
    entry.active = Boolean(timetableResponse.data.active)
    entry.teachers = teacherResponse.data
    if (!entry.teachers.some(teacher => teacher.id === entry.professor_id)) entry.professor_id = null
  } catch (error) {
    if (entry.data === requestedDate) entry.professor_id = null
  } finally {
    if (entry.data === requestedDate) entry.loading = false
  }
}

const openAbsencePanel = () => {
  absenceError.value = ''
  absenceEntries.value = [newAbsenceEntry()]
  absencePanelVisible.value = true
  loadAbsenceEntryContext(absenceEntries.value[0])
}

const addAbsenceEntry = () => {
  if (absenceEntries.value.length >= 3) return
  const entry = newAbsenceEntry()
  absenceEntries.value.push(entry)
  loadAbsenceEntryContext(entry)
}

const removeAbsenceEntry = (id) => {
  absenceEntries.value = absenceEntries.value.filter(entry => entry.id !== id)
}
const entryAllDay = (entry) => entry.periods.length === 9
const setEntryAllDay = (entry, checked) => {
  entry.periods = checked ? Array.from({ length: 9 }, (_, index) => index + 1) : []
}
const entryTeacherName = (entry) => entry.teachers.find(teacher => teacher.id === entry.professor_id)?.name

const applyDefaults = () => {
  for (const key of Object.keys(selectedCandidates)) delete selectedCandidates[key]
  for (const task of analysis.value?.tasks || []) {
    selectedCandidates[task.task_key] = task.recommended?.id || task.alternatives[0]?.id
  }
}

const createAndAnalyze = async () => {
  busy.value = 'analyze'
  absenceError.value = ''
  try {
    const created = (await axios.post('/api/absence-cases/batch', {
      items: absenceEntries.value.map(entry => ({
        professor_id: entry.professor_id,
        data: entry.data,
        periods: entry.periods.map(Number),
      })),
    }, { _silent: true })).data
    currentAbsenceIds.value = created.batch_absence_case_ids
    batchAnalyses.value = created.analyses || [{ ...created, date: absenceEntries.value[0].data }]
    const globalDate = iso(props.dataGlobal)
    const firstDate = batchAnalyses.value.some(item => item.date === globalDate) ? globalDate : batchAnalyses.value[0].date
    await selectAnalysisDate(firstDate, false)
    absencePanelVisible.value = false
    absenceEntries.value = []
  } catch (error) {
    absenceError.value = error.response?.data?.detail || t('app.errors.unexpected')
  } finally { busy.value = '' }
}

const selectAnalysisDate = async (targetDate, refresh = true) => {
  let selected = batchAnalyses.value.find(item => item.date === targetDate)
  if (!selected) return
  selectedAnalysisDate.value = targetDate
  if (refresh && selected.absence_case_ids?.length) {
    analysisSwitchLoading.value = true
    try {
      const latest = (await axios.post(`/api/absence-cases/${selected.absence_case_ids[0]}/analyze`)).data
      selected = { date: targetDate, ...latest }
      batchAnalyses.value = batchAnalyses.value.map(item => item.date === targetDate ? selected : item)
    } finally { analysisSwitchLoading.value = false }
  }
  analysis.value = selected
  applyDefaults()
}

const selectedForTask = (task) => task.alternatives.filter(item => item.id === selectedCandidates[task.task_key])
const dateLabel = (value) => new Intl.DateTimeFormat(locale.value === 'en' ? 'en-HK' : 'zh-HK', {
  month: 'numeric', day: 'numeric', weekday: 'short'
}).format(new Date(`${value}T12:00:00`))
const verifyTask = async (task) => {
  const candidate = selectedForTask(task)[0]
  if (!candidate) return
  verificationVisible.value = true
  verificationLoading.value = true
  verificationTimetables.value = []
  try {
    const dates = [...new Set(candidate.legs.flatMap(leg => [leg.from_date, leg.to_date]))].sort()
    const responses = await Promise.all(dates.map(async day => [
      day, (await axios.get('/api/effective-timetable', { params: { data: day } })).data.lessons || []
    ]))
    const lessonsByDate = Object.fromEntries(responses)
    const teacherNames = new Map()
    for (const leg of candidate.legs) {
      leg.teachers.forEach((id, index) => teacherNames.set(Number(id), leg.teacher_names[index] || String(id)))
      if (leg.replacement_teacher_id) teacherNames.set(Number(leg.replacement_teacher_id), leg.replacement_teacher_name)
    }
    verificationTimetables.value = [...teacherNames.entries()].map(([teacherId, name]) => ({
      id: teacherId,
      name,
      days: dates.map(day => ({
        date: day,
        slots: Array.from({ length: 9 }, (_, index) => {
          const period = index + 1
          const unchanged = lessonsByDate[day]
            .filter(lesson => lesson.period === period && lesson.teacher_ids.includes(teacherId))
            .filter(lesson => !candidate.legs.some(leg => leg.from_date === day && leg.occurrence_id === lesson.occurrence_id
              && (candidate.kind === 'emergency_cover' ? Number(leg.replaced_teacher_id) === teacherId : leg.teachers.map(Number).includes(teacherId))))
            .map(lesson => ({ ...lesson, key: lesson.occurrence_id, adjusted: false }))
          const adjusted = candidate.legs
            .filter(leg => leg.to_date === day && Number(leg.to_period) === period
              && (candidate.kind === 'emergency_cover' ? Number(leg.replacement_teacher_id) === teacherId : leg.teachers.map(Number).includes(teacherId)))
            .map((leg, legIndex) => ({ ...leg, key: `${candidate.id}-${legIndex}-${teacherId}`, adjusted: true }))
          return { period, lessons: [...adjusted, ...unchanged] }
        })
      }))
    }))
  } finally {
    verificationLoading.value = false
  }
}
const confirmTask = async (task) => {
  const candidateId = selectedCandidates[task.task_key]
  if (!candidateId) return
  busy.value = task.task_key
  try {
    const response = (await axios.post('/api/adjustments/confirm', {
      absence_case_id: task.absence_case_id, candidate_id: candidateId, expected_revision: analysis.value.revision
    })).data
    analysis.value = response.analysis
    batchAnalyses.value = batchAnalyses.value.map(item => item.date === selectedAnalysisDate.value
      ? { date: selectedAnalysisDate.value, ...response.analysis }
      : item)
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
  batchAnalyses.value = []
  selectedAnalysisDate.value = ''
  await loadDateContext(); await loadEffective()
}

const kindLabel = (kind) => t(`records.kinds.${kind}`, kind)
const sourceLabel = (source) => t(`rescheduling.sources.${source}`, source)
const leaveTypeLabel = (value) => t(`leave.types.${value}`, value)

const loadLeaves = async () => {
  const [leaveResponse, teacherResponse] = await Promise.all([
    axios.get('/api/teacher-leaves'), axios.get('/api/rescheduling/teachers')
  ])
  leaves.value = leaveResponse.data
  leaveTeachers.value = teacherResponse.data
}
const resetLeave = () => {
  editingLeaveId.value = null
  Object.assign(leave, { professor_id: null, leave_type: 'sick', start_date: '', end_date: '' })
}
const editLeave = (item) => {
  editingLeaveId.value = item.id
  Object.assign(leave, { professor_id: item.professor_id, leave_type: item.leave_type, start_date: item.start_date, end_date: item.end_date })
}
const saveLeave = async () => {
  leaveBusy.value = true
  try {
    const url = editingLeaveId.value ? `/api/teacher-leaves/${editingLeaveId.value}` : '/api/teacher-leaves'
    await axios[editingLeaveId.value ? 'put' : 'post'](url, leave)
    resetLeave()
    await Promise.all([loadLeaves(), loadDateContext(), loadEffective()])
  } finally { leaveBusy.value = false }
}
const removeLeave = async (id) => {
  await axios.delete(`/api/teacher-leaves/${id}`)
  if (editingLeaveId.value === id) resetLeave()
  await Promise.all([loadLeaves(), loadDateContext(), loadEffective()])
}

const resumeAbsence = async (record) => {
  busy.value = 'analyze'
  currentAbsenceIds.value = [record.entity_id]
  effectiveDate.value = record.date
  analysis.value = null
  try {
    timetable.value = (await axios.get('/api/timetables/current', { params: { data: record.date } })).data
    const result = (await axios.post(`/api/absence-cases/${record.entity_id}/analyze`)).data
    batchAnalyses.value = [{ date: record.date, ...result }]
    selectedAnalysisDate.value = record.date
    analysis.value = batchAnalyses.value[0]
    applyDefaults()
    await loadEffective()
  } finally { busy.value = '' }
}

defineExpose({ resumeAbsence })

onMounted(async () => {
  await Promise.all([loadDateContext(), loadEffective(), ...(props.isAdmin ? [loadLeaves()] : [])])
})
</script>

<style scoped>
.rescheduling-page { display: grid; gap: 1rem; color: var(--text-color-primary); }
.page-heading { display: flex; justify-content: space-between; gap: 2rem; align-items: center; padding: .15rem 0 .75rem; border-bottom: 1px solid var(--border-color); }
.page-heading h2 { margin: 0 0 .3rem; color: var(--primary-color-dark); font-size: clamp(1.55rem, 3vw, 1.95rem); line-height: 1.2; letter-spacing: -.025em; }
.page-heading p { max-width: 65ch; color: var(--text-color-secondary); }
.page-actions { display: flex; align-items: center; gap: 1rem; }
.revision { color: var(--text-color-secondary); font-size: .8rem; white-space: nowrap; }
.panel { min-width: 0; background: var(--card-background); border: 1px solid var(--border-color); border-radius: 4px; padding: 1.2rem; }
.panel-title { display: flex; align-items: center; justify-content: space-between; gap: 1rem; margin-bottom: 1rem; }
.panel-title > div { display: flex; align-items: center; gap: .65rem; }
.panel-title h3 { margin: 0; font-size: 1rem; }
.panel-title small { color: var(--text-color-secondary); }
.title-copy { display: flex; flex-direction: column; gap: .12rem; }
.analysis-actions { display: flex; align-items: center !important; gap: .45rem; }
.analysis-dates { display: flex; gap: 0; margin: -0.25rem 0 1rem; border-bottom: 1px solid var(--border-color); overflow-x: auto; }
.analysis-dates button { padding: .55rem .8rem; border: 0; border-bottom: 2px solid transparent; background: transparent; color: var(--text-color-secondary); cursor: pointer; font: inherit; font-size: .8rem; font-weight: 650; white-space: nowrap; }
.analysis-dates button:hover { color: var(--primary-color-dark); }
.analysis-dates button.active { border-bottom-color: var(--primary-color); color: var(--primary-color-dark); }
.analysis-dates button:focus-visible { box-shadow: var(--focus-ring); }
.analysis-dates button:disabled { cursor: wait; opacity: .6; }
.absence-sidebar-title h3 { margin: 0; color: var(--primary-color-dark); font-size: 1.1rem; }
.absence-sidebar-title p { margin: .25rem 0 0; color: var(--text-color-secondary); font-size: .82rem; font-weight: 400; }
.absence-form { display: flex; min-height: calc(100dvh - 7rem); flex-direction: column; gap: 1rem; }
.absence-entry { padding: 0 0 1.15rem; border-bottom: 1px solid var(--border-color); }
.absence-entry + .absence-entry { padding-top: .15rem; }
.absence-entry > header { display: flex; align-items: center; justify-content: space-between; min-height: 2.25rem; margin-bottom: .7rem; }
.absence-entry-grid { display: grid; grid-template-columns: 1.25fr 1fr; gap: .75rem; }
.absence-entry label { display: flex; flex-direction: column; gap: .35rem; color: #344054; font-size: .84rem; font-weight: 650; }
.entry-error, .absence-form-error { margin: .55rem 0 0; color: #9b3b30; font-size: .8rem; }
.add-entry-row { display: flex; align-items: center; justify-content: space-between; gap: .75rem; }
.add-entry-row small { color: var(--text-color-secondary); }
.absence-form-actions { display: flex; justify-content: flex-end; gap: .5rem; margin-top: auto; padding-top: 1rem; border-top: 1px solid var(--border-color); }
select, input[type=date], input[type=file], textarea { width: 100%; min-height: 2.55rem; border: 1px solid #c8d2dd; border-radius: 4px; padding: .6rem .7rem; background: #fff; color: var(--text-color-primary); }
select:hover, input:hover, textarea:hover { border-color: #aeb8c5; }
select:focus, input:focus, textarea:focus { border-color: var(--primary-color); }
input[type=checkbox] { accent-color: var(--primary-color); }
input[type=file] { padding: .45rem; }
.period-heading { display: flex; align-items: center; justify-content: space-between; gap: .75rem; font-size: .84rem; font-weight: 650; }
.absence-form .all-day { flex-direction: row; align-items: center; gap: .35rem; font-weight: 600; cursor: pointer; }
.all-day input { width: auto; min-height: auto; }
.periods { display: grid; grid-template-columns: repeat(3, 1fr); gap: .45rem; margin-top: .4rem; }
.periods label { display: flex; flex-direction: row; align-items: center; justify-content: center; border: 1px solid var(--border-color); border-radius: 3px; padding: .55rem !important; font-weight: 550 !important; cursor: pointer; }
.periods label:hover { border-color: #aeb8c5; background: var(--surface-soft); }
.periods label.selected { border-color: #6f91b1; background: var(--highlight-bg); color: var(--primary-color-dark); }
.periods input { width: auto; min-height: auto; }
.notice { padding: .8rem 1rem; border-radius: 3px; border-left: 3px solid currentColor; }
.warning { background: #fff8e8; color: #8a5b16; }
.success { background: #ebf8ef; color: #247147; }
.empty-state { display: grid; place-items: center; min-height: 230px; padding: 2rem; border-radius: 3px; background: var(--surface-soft); color: var(--text-color-secondary); text-align: center; }
.empty-state p { margin: 0 0 .9rem; }
.task-card { margin-bottom: .8rem; padding: 1rem; border: 1px solid var(--border-color); border-left: 3px solid #6f91b1; border-radius: 4px; }
.task-card:last-child { margin-bottom: 0; }
.task-heading { display: flex; justify-content: space-between; gap: 1rem; margin-bottom: .8rem; }
.task-heading div { display: flex; flex-direction: column; gap: .2rem; }
.task-heading small { color: var(--text-color-secondary); }
.status, .source-tag { display: inline-flex; align-items: center; width: fit-content; padding: .24rem .52rem; border-radius: 3px; background: #eef1f4; color: #596476; font-size: .74rem; white-space: nowrap; }
.status.recommended, .status.confirmed, .source-tag.changed { background: #e4f5e9; color: #216a42; }
.status.unresolved { background: #fdecea; color: #9b3b30; }
.movement-list { margin: .7rem 0; padding: .7rem .8rem; border-radius: 3px; background: var(--surface-soft); }
.movement-list div { display: flex; justify-content: space-between; gap: 1rem; padding: .3rem 0; font-size: .82rem; }
.movement-list b { color: var(--primary-color-dark); text-align: right; }
.candidate-actions { display: flex; justify-content: flex-end; gap: .55rem; }
.verification-loading { display: grid; min-height: 180px; place-items: center; color: var(--text-color-secondary); }
.verification-content > p { margin: 0 0 1rem; color: var(--text-color-secondary); }
.verification-teacher + .verification-teacher { margin-top: 1rem; }
.verification-teacher h4 { margin: 0 0 .45rem; }
.verification-wrap { overflow-x: auto; border: 1px solid var(--border-color); border-radius: 4px; }
.verification-timetable { min-width: 1000px; table-layout: fixed; font-size: .75rem; }
.verification-timetable th, .verification-timetable td { width: 100px; height: 66px; padding: .4rem; vertical-align: top; }
.verification-timetable th:first-child { width: 88px; }
.verification-lesson { display: flex; flex-direction: column; gap: .05rem; padding: .3rem; border-radius: 5px; color: #596476; }
.verification-lesson + .verification-lesson { margin-top: .2rem; }
.verification-lesson.adjusted { background: #def1e5; color: #216a42; }
.verification-lesson small { font-size: .62rem; font-weight: 700; }
.verification-lesson strong { font-size: .72rem; }
.verification-lesson span { overflow: hidden; font-size: .65rem; text-overflow: ellipsis; white-space: nowrap; }
.unresolved-copy { margin: 0; color: #9b493d; }
.effective-filters { display: flex; align-items: center; gap: 1rem; }
.effective-panel .inline-date { display: flex; align-items: center; gap: .55rem; color: var(--text-color-secondary); font-size: .82rem; }
.effective-panel .inline-date input { width: auto; }
.affected-view-bar { display: flex; align-items: center; justify-content: space-between; gap: 1rem; margin-bottom: .75rem; }
.view-switch { display: inline-flex; padding: .2rem; border-radius: 4px; background: var(--surface-soft); }
.view-switch button { padding: .42rem .7rem; border: 0; border-radius: 3px; background: transparent; color: var(--text-color-secondary); cursor: pointer; font-size: .78rem; font-weight: 650; transition: background .15s ease, color .15s ease; }
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
.affected-card { min-width: 0; padding: 1rem; border: 1px solid var(--border-color); border-left: 3px solid #6f91b1; border-radius: 4px; background: #fff; }
.affected-card header { display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; margin-bottom: .8rem; }
.affected-card-title { display: flex; flex-wrap: wrap; align-items: center; gap: .45rem .7rem; }
.affected-card header strong { font-size: 1rem; }
.affected-card-title > span:not(.source-tag) { color: var(--text-color-secondary); font-size: .78rem; }
.cycle-route { display: flex; align-items: center; gap: .3rem; color: #216a42; }
.cycle-route-step { display: grid; width: 1.45rem; height: 1.45rem; place-items: center; border: 1px solid #70a086; border-radius: 50%; font-size: .7rem; font-weight: 750; font-variant-numeric: tabular-nums; }
.cycle-route-arrow { color: #70a086; font-size: .85rem; }
.cycle-table-wrap { overflow-x: auto; border: 1px solid var(--border-color); border-radius: 4px; }
.cycle-table { min-width: 720px; font-size: .8rem; }
.cycle-table th, .cycle-table td { padding: .65rem .75rem; vertical-align: middle; }
.cycle-table th { background: #f8faf9; color: #596476; font-size: .72rem; }
.cycle-table td { color: var(--text-color-primary); }
.cycle-table tbody tr:hover { background: #fbfdfc; }
.cycle-table .cycle-order { width: 3rem; text-align: center; }
.cycle-order span { display: grid; width: 1.65rem; height: 1.65rem; margin: auto; place-items: center; border-radius: 50%; background: #2f7d55; color: #fff; font-size: .72rem; font-weight: 750; }
.cycle-table .cycle-table-arrow { width: 2rem; padding-inline: .2rem; color: #70a086; text-align: center; }
.cycle-table th.cycle-table-arrow { color: transparent; }
.cycle-table strong { white-space: nowrap; }
.cycle-teacher { color: var(--text-color-secondary) !important; white-space: nowrap; }
.cycle-time { font-variant-numeric: tabular-nums; white-space: nowrap; }
.cover-link { display: grid; grid-template-columns: minmax(170px, auto) auto minmax(220px, 1fr); align-items: center; gap: .75rem; padding: .8rem; border-radius: 4px; background: #fff8e5; }
.cover-link > div { display: flex; flex-direction: column; gap: .15rem; }
.cover-link small, .cover-link div span { color: var(--text-color-secondary); font-size: .72rem; }
.cover-link > span { color: #a57516; font-size: 1.2rem; font-weight: 800; }
.cover-link b { color: #805c12; font-size: .8rem; }
.affected-empty { display: grid; min-height: 110px; place-items: center; border-radius: 3px; background: var(--surface-soft); color: var(--text-color-secondary); text-align: center; }
.mini-timetable-wrap { overflow-x: auto; border: 1px solid var(--border-color); border-radius: 4px; }
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
table { width: 100%; min-width: 640px; border-collapse: collapse; font-size: .86rem; }
th, td { padding: .72rem .75rem; border-bottom: 1px solid #edf0f3; text-align: left; }
th { background: var(--surface-soft); color: var(--text-color-secondary); font-size: .78rem; font-weight: 700; white-space: nowrap; }
tbody tr:last-child td { border-bottom: 0; }
tbody tr:hover { background: #fbfcfe; }
.leave-heading, .leave-list article { display: flex; align-items: center; justify-content: space-between; gap: 1rem; }
.leave-heading { align-items: flex-start; }
.leave-heading h3 { margin: 0 0 .3rem; }
.leave-heading p, .leave-list span { color: var(--text-color-secondary); }
.leave-form { display: grid; grid-template-columns: 1.2fr 1fr .8fr .8fr auto; align-items: end; gap: .75rem; margin: 1rem 0; }
.leave-form label { display: flex; flex-direction: column; gap: .35rem; color: #344054; font-size: .82rem; font-weight: 650; }
.leave-list article { padding: .75rem 0; border-top: 1px solid #edf0f3; }
.leave-list article > div:first-child { display: flex; flex-direction: column; gap: .2rem; }
.leave-list span { font-size: .82rem; }
.empty-state.compact { min-height: 80px; }
@media (max-width: 900px) {
  .leave-form { grid-template-columns: 1fr 1fr; }
  .leave-form .p-button { grid-column: 1 / -1; }
  .movement-list div { flex-direction: column; gap: .2rem; }
  .movement-list b { text-align: left; }
}

@media (max-width: 600px) {
  :deep(.absence-sidebar) { width: 100vw !important; max-width: 100vw; }
  .page-heading { flex-direction: column; gap: .35rem; }
  .page-actions { width: 100%; justify-content: space-between; }
  .panel-title { align-items: flex-start; }
  .effective-panel .panel-title { flex-direction: column; }
  .effective-filters { width: 100%; align-items: flex-start; flex-direction: column-reverse; }
  .affected-view-bar { align-items: flex-start; flex-direction: column; }
  .analysis-actions { align-items: flex-end !important; flex-direction: column; }
  .task-heading { flex-direction: column; }
  .candidate-actions { align-items: stretch; flex-direction: column; }
  .affected-card header { align-items: stretch; flex-direction: column; }
  .cycle-route { justify-content: flex-end; }
  .leave-heading, .leave-list article { align-items: flex-start; flex-direction: column; }
  .leave-form { grid-template-columns: 1fr; }
  .absence-entry-grid { grid-template-columns: 1fr; }
  .add-entry-row { align-items: flex-start; flex-direction: column; }
  .panel { padding: 1rem; }
}
</style>
