<template>
  <section class="import-page">
    <header class="page-heading">
      <div>
        <h2>{{ $t('importCenter.title') }}</h2>
        <p>{{ $t('importCenter.description') }}</p>
      </div>
      <span class="revision">{{ $t('rescheduling.revision', { revision: timetable.revision ?? '-' }) }}</span>
    </header>

    <section class="panel">
      <h3>{{ $t('importCenter.baseTitle') }}</h3>
      <div v-if="can('timetable.upload')" class="import-grid">
        <label>{{ $t('importCenter.scheduleType') }}<select v-model="scheduleType" :disabled="Boolean(preview)" @change="classFile = null; teacherFile = null; uploadInputKey += 1"><option value="normal">{{ $t('importCenter.normalType') }}</option><option value="post_exam">{{ $t('importCenter.postExamType') }}</option></select></label>
        <label>{{ $t(scheduleType === 'post_exam' ? 'importCenter.postExamClassFile' : 'importCenter.classFile') }}<input :key="`class-${uploadInputKey}`" type="file" :accept="scheduleType === 'post_exam' ? '.xlsx' : '.xls'" @change="classFile = $event.target.files[0]" /></label>
        <label>{{ $t('importCenter.teacherFile') }}<input :key="`teacher-${uploadInputKey}`" type="file" accept=".xlsx" @change="teacherFile = $event.target.files[0]" /></label>
        <label>{{ $t('importCenter.effectiveFrom') }}<input v-model="effectiveFrom" type="date" /></label>
        <label>{{ $t('importCenter.effectiveTo') }}<input v-model="effectiveTo" type="date" /></label>
        <Button :label="$t('importCenter.check')" icon="pi pi-search" class="progress-fill-button" :class="{ 'is-progressing': busy === 'preview' }" :loading="busy === 'preview'" :disabled="!filesReady || !effectiveFrom || !effectiveTo" @click="previewImport" />
      </div>
      <p v-if="timetable.active" class="muted">{{ $t('importCenter.currentFiles', { date: timetable.query_date, classFile: timetable.class_filename, teacherFile: timetable.teacher_filename }) }}</p>
      <p v-else class="notice warning">{{ $t('importCenter.noCurrent') }}</p>
    </section>

    <section class="panel">
      <div class="result-heading">
        <div><h3>{{ $t('importCenter.versionsTitle') }}</h3><p class="muted">{{ $t('importCenter.versionsHint') }}</p></div>
      </div>
      <div class="table-wrap">
        <table class="versions-table">
          <thead><tr><th>{{ $t('importCenter.dateRange') }}</th><th>{{ $t('importCenter.files') }}</th><th>{{ $t('importCenter.scale') }}</th><th>{{ $t('importCenter.linkedRecords') }}</th><th>{{ $t('importCenter.status') }}</th><th>{{ $t('importCenter.actions') }}</th></tr></thead>
          <TransitionGroup name="motion-list" tag="tbody">
            <tr v-for="version in versions" :key="version.id" :class="{ 'version-dirty': versionChanged(version) }">
              <td class="version-range-cell">
                <div class="version-range-editor">
                  <label><span>{{ $t('importCenter.startDate') }}</span><input v-model="version.draft_effective_from" type="date" :disabled="!can('timetable.manage')" @input="message = ''" /></label>
                  <label><span>{{ $t('importCenter.endDate') }}</span><input v-model="version.draft_effective_to" type="date" :disabled="!can('timetable.manage')" @input="message = ''" /></label>
                  <div v-if="can('timetable.manage') && versionChanged(version)" class="version-date-actions">
                    <span class="status unsaved">{{ $t('importCenter.unsaved') }}</span>
                    <Button :label="$t('importCenter.saveChanges')" size="small" :loading="busy === `version-${version.id}`" :disabled="!version.draft_effective_from || !version.draft_effective_to" @click="saveVersion(version)" />
                    <Button :label="$t('importCenter.cancelChanges')" size="small" text :disabled="busy === `version-${version.id}`" @click="resetVersion(version)" />
                  </div>
                </div>
              </td>
              <td :data-label="$t('importCenter.files')"><div class="file-list"><span>{{ version.class_filename }}</span><span>{{ version.teacher_filename }}</span></div></td>
              <td :data-label="$t('importCenter.scale')">
                {{ $t('importCenter.scaleValue', { lessons: version.lessons, teachers: version.teachers }) }}
                <details class="version-specials">
                  <summary>{{ $t('importCenter.specialCount', { count: version.draft_special_subjects.length }) }}</summary>
                  <div>
                    <label v-for="subject in version.subjects" :key="subject" :class="{ selected: version.draft_special_subjects.includes(subject) }">
                      <input v-model="version.draft_special_subjects" type="checkbox" :value="subject" :disabled="!can('timetable.manage')" @change="message = ''" />{{ subject }}
                    </label>
                  </div>
                </details>
              </td>
              <td :data-label="$t('importCenter.linkedRecords')">{{ $t('importCenter.recordValue', { absences: version.absence_records, adjustments: version.adjustment_records }) }}</td>
              <td :data-label="$t('importCenter.status')"><span :class="['status', version.locked ? 'locked' : 'available']">{{ version.locked ? $t('importCenter.locked') : $t('importCenter.available') }}</span><span v-if="version.is_current" class="status current">{{ $t('importCenter.current') }}</span></td>
              <td :data-label="$t('importCenter.actions')"><Button v-if="can('timetable.manage')" :label="$t('common.delete')" size="small" severity="danger" outlined :disabled="version.locked" @click="removeVersion(version)" /></td>
            </tr>
            <tr v-if="!versions.length"><td colspan="6" class="empty-row">{{ $t('importCenter.noVersions') }}</td></tr>
          </TransitionGroup>
        </table>
      </div>
    </section>

    <Transition name="motion-fade">
    <div v-if="preview" class="preview-stack">
      <section class="summary-grid">
        <div><strong>{{ preview.classes }}</strong><span>{{ $t('importCenter.classes') }}</span></div>
        <div><strong>{{ preview.teachers }}</strong><span>{{ $t('importCenter.teachers') }}</span></div>
        <div><strong>{{ preview.lessons }}</strong><span>{{ $t('importCenter.lessons') }}</span></div>
        <div :class="{ alert: preview.blocked_lessons }"><strong>{{ preview.blocked_lessons }}</strong><span>{{ $t('importCenter.blocked') }}</span></div>
      </section>

      <section class="panel">
        <div class="result-heading">
          <div><h3>{{ $t('importCenter.resultTitle') }}</h3><p class="muted">{{ $t('importCenter.resultHint') }}</p></div>
          <div class="result-actions">
            <Button v-if="can('timetable.upload')" :label="$t('importCenter.cancelUpload')" severity="danger" text :loading="busy === 'discard'" @click="discardPreview" />
            <Button v-if="can('timetable.manage')" :label="$t('importCenter.activate')" icon="pi pi-check" severity="success" :loading="busy === 'activate'" :disabled="hasErrors || hasUnresolvedReviews || !effectiveFrom || !effectiveTo" @click="activateImport" />
          </div>
        </div>
        <fieldset class="special-subjects">
          <legend>{{ $t('importCenter.specialSubjects') }}</legend>
          <p class="muted">{{ $t('importCenter.specialSubjectsHint') }}</p>
          <div>
            <label v-for="subject in preview.subjects" :key="subject" :class="{ selected: specialSubjects.includes(subject) }">
              <input v-model="specialSubjects" type="checkbox" :value="subject" :disabled="!can('timetable.manage')" />{{ subject }}
            </label>
          </div>
        </fieldset>
        <TransitionGroup v-if="preview.warnings.length" name="motion-list" tag="ul" class="warnings">
          <li v-for="warning in preview.warnings" :key="warning">{{ warning }}</li>
        </TransitionGroup>
        <p v-if="hasErrors" class="notice danger">{{ $t('importCenter.errorsBlock') }}</p>
        <p v-else-if="hasUnresolvedReviews" class="notice warning">{{ $t('importCenter.reviewsProgress', { confirmed: confirmedReviewCount, total: reviewIds.length, remaining: unresolvedReviewCount }) }}</p>
        <div v-if="can('timetable.upload') && reviewIds.length" class="bulk-actions">
          <label><input type="checkbox" :checked="allReviewsSelected" @change="toggleAllReviews" />{{ $t('importCenter.selectAllReviews') }}</label>
          <span>{{ $t('importCenter.selectedReviews', { count: selectedReviewIds.length }) }}</span>
          <Button :label="$t('importCenter.clearSelection')" text size="small" :disabled="!selectedReviewIds.length" @click="selectedReviewIds = []" />
          <Button :label="bulkClassLabel" size="small" outlined :disabled="!selectedReviewIds.length" @click="applyBulk('class')" />
          <Button :label="bulkTeacherLabel" size="small" :disabled="!selectedReviewIds.length" @click="applyBulk('teacher')" />
          <Button :label="$t('importCenter.confirmSelected')" icon="pi pi-check" severity="success" size="small" :loading="busy === 'save-selected'" :disabled="!canConfirmSelected" @click="saveResolutions(selectedReviewIds, 'save-selected')" />
        </div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>{{ $t('importCenter.selectReview') }}</th><th>{{ $t('importCenter.severity') }}</th><th>{{ $t('importCenter.weekdayPeriod') }}</th><th>{{ $t('rescheduling.class') }}</th><th>{{ $t('rescheduling.subject') }}</th><th>{{ $t('rescheduling.teacherColumn') }}</th><th>{{ $t('importCenter.classWorkbook') }}</th><th>{{ $t('importCenter.teacherWorkbook') }}</th><th>{{ $t('importCenter.decision') }}</th></tr></thead>
            <TransitionGroup name="motion-list" tag="tbody">
              <tr v-for="(issue, index) in preview.issues" :key="issue.resolution_id || index">
                <td><input v-if="can('timetable.upload') && issue.severity === 'review'" v-model="selectedReviewIds" type="checkbox" :value="resolutionId(issue)" /></td>
                <td><span :class="['status', issue.severity]">{{ issue.severity === 'error' ? $t('common.error') : $t('importCenter.review') }}</span></td>
                <td>{{ weekdayLabel(issue.weekday) }} {{ $t('records.period', { period: issue.period }) }}</td>
                <td>{{ issue.class_code }}</td><td>{{ issue.subject }}</td><td>{{ issue.teacher || '-' }}</td>
                <td>{{ issue.class_workbook }}</td><td>{{ issue.teacher_workbook }}</td>
                <td>
                  <div v-if="issue.severity === 'review'" class="resolution-cell">
                    <div class="resolution-choice">
                      <label :class="{ selected: resolutions[resolutionId(issue)] === 'class' }"><input v-model="resolutions[resolutionId(issue)]" type="radio" :name="resolutionId(issue)" value="class" :disabled="!can('timetable.upload')" />{{ $t(issue.code === 'teacher_extra_assignment' ? 'importCenter.ignoreExtraTeacher' : 'importCenter.useClassWorkbook') }}</label>
                      <label :class="{ selected: resolutions[resolutionId(issue)] === 'teacher' }"><input v-model="resolutions[resolutionId(issue)]" type="radio" :name="resolutionId(issue)" value="teacher" :disabled="!can('timetable.upload')" />{{ $t(issue.code === 'teacher_extra_assignment' ? 'importCenter.addCoTeacher' : 'importCenter.useTeacherWorkbook') }}</label>
                    </div>
                    <Button
                      v-if="can('timetable.upload')"
                      :label="$t(isResolutionConfirmed(issue) ? 'importCenter.confirmedDecision' : 'importCenter.confirmThisDecision')"
                      icon="pi pi-check"
                      size="small"
                      :outlined="!isResolutionConfirmed(issue)"
                      :severity="isResolutionConfirmed(issue) ? 'success' : undefined"
                      :loading="busy === `resolution-${resolutionId(issue)}`"
                      :disabled="!resolutions[resolutionId(issue)] || isResolutionConfirmed(issue)"
                      @click="saveResolutions([resolutionId(issue)], `resolution-${resolutionId(issue)}`)"
                    />
                  </div>
                  <span v-else class="muted">{{ $t('importCenter.fixSource') }}</span>
                </td>
              </tr>
              <tr v-if="!preview.issues.length"><td colspan="9" class="empty-row">{{ $t('importCenter.perfectMatch') }}</td></tr>
            </TransitionGroup>
          </table>
        </div>
      </section>
    </div>
    </Transition>

    <Transition name="motion-fade"><p v-if="message" class="notice success">{{ message }}</p></Transition>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import axios from 'axios'
import Button from 'primevue/button'

const { t } = useI18n()
defineProps({ can: { type: Function, required: true } })

const timetable = ref({ active: false })
const versions = ref([])
const scheduleType = ref('normal')
const classFile = ref(null)
const teacherFile = ref(null)
const effectiveFrom = ref('')
const effectiveTo = ref('')
const preview = ref(null)
const busy = ref('')
const message = ref('')
const resolutions = ref({})
const savedResolutions = ref({})
const selectedReviewIds = ref([])
const specialSubjects = ref([])
const uploadInputKey = ref(0)
const resolutionId = (issue) => issue.resolution_id || `${issue.weekday}:${issue.period}:${issue.class_code}:${issue.teacher}`
const reviewIds = computed(() => (preview.value?.issues || [])
  .filter(issue => issue.severity === 'review')
  .map(resolutionId))
const filesReady = computed(() => Boolean(classFile.value && teacherFile.value))
const allReviewsSelected = computed(() => reviewIds.value.length > 0 && selectedReviewIds.value.length === reviewIds.value.length)
const hasErrors = computed(() => preview.value?.issues.some(issue => issue.severity === 'error'))
const isResolutionConfirmed = (issue) => Boolean(savedResolutions.value[resolutionId(issue)])
  && savedResolutions.value[resolutionId(issue)] === resolutions.value[resolutionId(issue)]
const confirmedReviewCount = computed(() => (preview.value?.issues || []).filter(
  issue => issue.severity === 'review' && isResolutionConfirmed(issue)
).length)
const unresolvedReviewCount = computed(() => reviewIds.value.length - confirmedReviewCount.value)
const hasUnresolvedReviews = computed(() => unresolvedReviewCount.value > 0)
const selectedIssues = computed(() => (preview.value?.issues || []).filter(issue => selectedReviewIds.value.includes(resolutionId(issue))))
const selectedIssueType = computed(() => {
  if (!selectedIssues.value.length) return 'none'
  if (selectedIssues.value.every(issue => issue.code === 'teacher_extra_assignment')) return 'extra'
  if (selectedIssues.value.every(issue => issue.code !== 'teacher_extra_assignment')) return 'mismatch'
  return 'mixed'
})
const bulkClassLabel = computed(() => t(selectedIssueType.value === 'extra' ? 'importCenter.bulkIgnoreExtraTeacher'
  : selectedIssueType.value === 'mismatch' ? 'importCenter.bulkUseClassWorkbook' : 'importCenter.bulkLeftDecision'))
const bulkTeacherLabel = computed(() => t(selectedIssueType.value === 'extra' ? 'importCenter.bulkAddCoTeacher'
  : selectedIssueType.value === 'mismatch' ? 'importCenter.bulkUseTeacherWorkbook' : 'importCenter.bulkRightDecision'))
const canConfirmSelected = computed(() => selectedReviewIds.value.length > 0
  && selectedReviewIds.value.every(id => resolutions.value[id])
  && selectedReviewIds.value.some(id => savedResolutions.value[id] !== resolutions.value[id]))
const sameItems = (left, right) => left.length === right.length && left.every(item => right.includes(item))
const versionChanged = (version) => version.draft_effective_from !== version.effective_from
  || version.draft_effective_to !== version.effective_to
  || !sameItems(version.draft_special_subjects, version.special_subjects)
const hasUnsavedVersions = computed(() => versions.value.some(versionChanged))

const resetVersion = (version) => {
  version.draft_effective_from = version.effective_from
  version.draft_effective_to = version.effective_to || ''
  version.draft_special_subjects = [...version.special_subjects]
}
const resetAllVersions = () => versions.value.forEach(resetVersion)

const handleBeforeUnload = (event) => {
  if (!hasUnsavedVersions.value) return
  event.preventDefault()
  event.returnValue = ''
}

defineExpose({ hasUnsavedChanges: () => hasUnsavedVersions.value, resetUnsavedChanges: resetAllVersions })

const toggleAllReviews = (event) => {
  selectedReviewIds.value = event.target.checked ? [...reviewIds.value] : []
}
const applyBulk = (choice) => {
  resolutions.value = {
    ...resolutions.value,
    ...Object.fromEntries(selectedReviewIds.value.map(id => [id, choice]))
  }
}

const saveResolutions = async (ids, busyKey) => {
  const decisions = Object.fromEntries(ids
    .filter(id => resolutions.value[id])
    .map(id => [id, resolutions.value[id]]))
  if (!Object.keys(decisions).length) return
  busy.value = busyKey; message.value = ''
  try {
    const response = (await axios.put(`/api/timetables/import/${preview.value.preview_id}/resolutions`, {
      resolutions: decisions
    })).data
    savedResolutions.value = response.saved_resolutions
    message.value = response.remaining_count
      ? t('importCenter.progressSaved', { confirmed: response.confirmed_count, total: reviewIds.value.length, remaining: response.remaining_count })
      : t('importCenter.allDecisionsConfirmed')
  } finally { busy.value = '' }
}

const loadCurrent = async () => {
  const [currentResponse, versionsResponse] = await Promise.all([
    axios.get('/api/timetables/current'), axios.get('/api/timetables')
  ])
  timetable.value = currentResponse.data
  versions.value = versionsResponse.data.map(version => ({
    ...version, draft_effective_from: version.effective_from, draft_effective_to: version.effective_to || '',
    draft_special_subjects: [...version.special_subjects]
  }))
}

const saveVersion = async (version) => {
  busy.value = `version-${version.id}`; message.value = ''
  try {
    await axios.put(`/api/timetables/${version.id}`, {
      effective_from: version.draft_effective_from, effective_to: version.draft_effective_to,
      special_subjects: version.draft_special_subjects
    })
    message.value = t('importCenter.versionUpdated', {
      start: version.draft_effective_from, end: version.draft_effective_to
    })
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
    form.append('schedule_type', scheduleType.value)
    form.append('class_workbook', classFile.value)
    form.append('teacher_workbook', teacherFile.value)
    preview.value = (await axios.post('/api/timetables/import/preview', form)).data
    specialSubjects.value = preview.value.subjects.filter(subject => /體育|視藝|美術|中默|英默|默書|默寫|聽寫|P\.?E\.?/i.test(subject))
    resolutions.value = {}
    savedResolutions.value = {}
    selectedReviewIds.value = []
  } finally { busy.value = '' }
}

const activateImport = async () => {
  busy.value = 'activate'; message.value = ''
  try {
    await axios.post(`/api/timetables/import/${preview.value.preview_id}/activate`, {
      effective_from: effectiveFrom.value, effective_to: effectiveTo.value,
      resolutions: resolutions.value, special_subjects: specialSubjects.value
    })
    message.value = t('importCenter.activated', { start: effectiveFrom.value, end: effectiveTo.value })
    preview.value = null
    resolutions.value = {}
    savedResolutions.value = {}
    selectedReviewIds.value = []
    specialSubjects.value = []
    await loadCurrent()
  } finally { busy.value = '' }
}

const discardPreview = async () => {
  busy.value = 'discard'; message.value = ''
  try {
    await axios.delete(`/api/timetables/import/${preview.value.preview_id}`)
    preview.value = null
    classFile.value = null
    teacherFile.value = null
    resolutions.value = {}
    savedResolutions.value = {}
    selectedReviewIds.value = []
    specialSubjects.value = []
    uploadInputKey.value += 1
    message.value = t('importCenter.uploadCancelled')
  } finally { busy.value = '' }
}

const weekdayLabel = (weekday) => t(`importCenter.weekdays.${weekday}`, `${weekday}`)

onMounted(() => {
  window.addEventListener('beforeunload', handleBeforeUnload)
  loadCurrent()
})
onBeforeUnmount(() => window.removeEventListener('beforeunload', handleBeforeUnload))
</script>

<style scoped>
.import-page { display: grid; gap: 1.25rem; color: var(--text-color-primary); }
.page-heading, .result-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 1.5rem; }
.result-actions { display: flex; align-items: center; gap: .45rem; }
.page-heading h2 { margin: 0 0 .35rem; font-size: clamp(1.65rem, 3vw, 2.15rem); line-height: 1.15; letter-spacing: -.035em; }
.page-heading p, .muted { color: var(--text-color-secondary); }
.revision { padding-top: .4rem; color: var(--text-color-secondary); font-size: var(--font-supporting); white-space: nowrap; }
.special-subjects { margin: 1rem 0; padding: 1rem; border: 1px solid var(--border-color); border-radius: 10px; }
.special-subjects legend { padding: 0 .35rem; font-size: var(--font-data); font-weight: 700; }
.special-subjects p { margin: 0 0 .65rem; font-size: var(--font-supporting); }
.special-subjects > div { display: flex; flex-wrap: wrap; gap: .45rem; }
.special-subjects label { display: flex; align-items: center; gap: .35rem; padding: .42rem .6rem; border: 1px solid var(--border-color); border-radius: 7px; cursor: pointer; font-size: var(--font-ui); }
.special-subjects label.selected { border-color: #d3aa52; background: #fff6db; color: #72500b; }
.panel { min-width: 0; padding: 1.25rem; border: 1px solid var(--border-color); border-radius: var(--radius-lg); background: var(--card-background); box-shadow: var(--shadow-panel); }
.preview-stack { display: grid; gap: 1.25rem; }
.panel h3 { margin: 0 0 .9rem; }
.result-heading h3 { margin: 0; }
.import-grid { display: grid; grid-template-columns: .7fr 1fr 1fr .62fr .62fr auto; align-items: end; gap: .8rem; }
.import-grid label { display: flex; flex-direction: column; gap: .35rem; color: #344054; font-size: var(--font-ui); font-weight: 650; }
input { width: 100%; min-height: 2.55rem; padding: .6rem .7rem; border: 1px solid #cfd6df; border-radius: 8px; background: #fff; color: var(--text-color-primary); }
input:hover { border-color: #aeb8c5; }
input:focus { border-color: var(--primary-color); }
input[type=file] { padding: .45rem; }
input[type=checkbox] { width: auto; min-height: auto; accent-color: var(--primary-color); }
.summary-grid { display: grid; grid-template-columns: repeat(4, 1fr); overflow: hidden; border: 1px solid var(--border-color); border-radius: 12px; background: var(--card-background); }
.summary-grid div { display: flex; flex-direction: column; padding: 1rem 1.1rem; border-left: 1px solid var(--border-color); }
.summary-grid div:first-child { border-left: 0; }
.summary-grid strong { font-size: 1.7rem; letter-spacing: -.03em; }
.summary-grid span { color: var(--text-color-secondary); font-size: var(--font-ui); }
.summary-grid .alert { background: #fff8e8; color: #84590e; }
.warnings { margin: .9rem 0; padding-left: 1.2rem; color: #87591d; }
.bulk-actions { display: flex; flex-wrap: wrap; align-items: center; gap: .55rem; margin-top: .9rem; padding: .7rem .8rem; border: 1px solid var(--border-color); border-radius: 9px; background: var(--surface-soft); }
.bulk-actions label { display: inline-flex; align-items: center; gap: .4rem; color: #344054; font-size: var(--font-ui); font-weight: 650; cursor: pointer; }
.bulk-actions label input { width: auto; min-height: auto; margin: 0; }
.bulk-actions > span { margin-right: auto; color: var(--text-color-secondary); font-size: var(--font-supporting); }
.table-wrap { overflow: auto; margin-top: 1rem; border: 1px solid var(--border-color); border-radius: 10px; }
table { width: 100%; border-collapse: collapse; font-size: var(--font-data); }
th, td { padding: .72rem .75rem; border-bottom: 1px solid #edf0f3; text-align: left; white-space: nowrap; }
th { background: var(--surface-soft); color: var(--text-color-secondary); font-size: var(--font-ui); font-weight: 700; }
tbody tr:last-child td { border-bottom: 0; }
tbody tr:hover { background: #fbfcfe; }
.file-list { display: flex; flex-direction: column; gap: .2rem; max-width: 260px; }
.file-list span { overflow: hidden; text-overflow: ellipsis; }
.version-range-cell { min-width: 430px; }
.version-range-editor { display: flex; flex-wrap: wrap; align-items: flex-end; gap: .55rem; }
.version-range-editor label { display: grid; gap: .25rem; color: var(--text-color-secondary); font-size: var(--font-supporting); font-weight: 650; }
.version-range-editor input { width: 165px; }
.version-date-actions { display: flex; flex-wrap: wrap; align-items: center; gap: .35rem; width: 100%; }
.version-dirty .version-range-cell { background: #fffaf0; box-shadow: inset 3px 0 #d3aa52; }
.version-specials { margin-top: .35rem; }
.version-specials summary { color: var(--primary-color-dark); cursor: pointer; font-size: var(--font-ui); font-weight: 650; }
.version-specials > div { display: flex; max-width: 420px; flex-wrap: wrap; gap: .3rem; padding-top: .45rem; white-space: normal; }
.version-specials label { display: inline-flex; align-items: center; gap: .25rem; padding: .28rem .4rem; border: 1px solid var(--border-color); border-radius: 6px; cursor: pointer; font-size: var(--font-supporting); }
.version-specials label.selected { border-color: #d3aa52; background: #fff6db; color: #72500b; }
.resolution-choice { display: flex; gap: .35rem; }
.resolution-cell { display: flex; align-items: center; gap: .5rem; }
.resolution-choice label { display: inline-flex; align-items: center; gap: .3rem; padding: .42rem .55rem; border: 1px solid #d6dce5; border-radius: 7px; cursor: pointer; }
.resolution-choice label.selected { border-color: var(--primary-color); background: var(--highlight-bg); color: var(--primary-color-dark); }
.resolution-choice input { width: auto; min-height: 0; margin: 0; }
.status { display: inline-flex; align-items: center; padding: .24rem .52rem; border-radius: 999px; background: #fff4d6; color: #84590e; font-size: var(--font-supporting); white-space: nowrap; }
.status + .status { margin-left: .35rem; }
.status.error, .status.locked { background: #fdecea; color: #9b3b30; }
.status.available { background: #e4f5e9; color: #216a42; }
.status.current { background: var(--highlight-bg); color: var(--primary-color-dark); }
.notice { padding: .8rem 1rem; border-radius: 8px; border-left: 3px solid currentColor; }
.warning { background: #fff8e8; color: #8a5b16; }
.danger { background: #fdecea; color: #96382f; }
.success { background: #ebf8ef; color: #247147; }
.empty-row { text-align: center; color: var(--text-color-secondary); }

@media (max-width: 1000px) {
  .import-grid { grid-template-columns: 1fr 1fr; }
  .import-grid .p-button { grid-column: 1 / -1; }
  .versions-table, .versions-table tbody { display: block; }
  .versions-table thead { display: none; }
  .versions-table tr { display: grid; grid-template-columns: 1fr 1fr; gap: .8rem 1rem; padding: 1rem; border-bottom: 1px solid var(--border-color); }
  .versions-table td { display: block; padding: 0; border: 0; white-space: normal; }
  .versions-table td:not(.version-range-cell)::before { content: attr(data-label); display: block; margin-bottom: .25rem; color: var(--text-color-secondary); font-size: var(--font-supporting); font-weight: 700; }
  .versions-table .version-range-cell { grid-column: 1 / -1; min-width: 0; padding: .7rem; }
  .versions-table .empty-row { grid-column: 1 / -1; }
}

@media (max-width: 600px) {
  .page-heading, .result-heading { flex-direction: column; }
  .revision { padding-top: 0; }
  .import-grid { grid-template-columns: 1fr; }
  .summary-grid { grid-template-columns: 1fr 1fr; }
  .summary-grid div:nth-child(3) { border-top: 1px solid var(--border-color); border-left: 0; }
  .summary-grid div:nth-child(4) { border-top: 1px solid var(--border-color); }
  .result-actions { width: 100%; }
  .result-actions .p-button { flex: 1; }
  .versions-table tr { grid-template-columns: 1fr; }
  .versions-table .version-range-cell, .versions-table .empty-row { grid-column: auto; }
  .version-range-editor label, .version-range-editor input { width: 100%; }
}
</style>
