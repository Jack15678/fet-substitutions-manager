<template>
  <Dialog
    :visible="visible"
    modal
    :header="$t('importCenter.calendar.dialogTitle')"
    :style="{ width: 'min(96vw, 960px)' }"
    :content-style="{ maxHeight: '72vh', overflow: 'auto' }"
    @update:visible="onVisibilityChange"
  >
    <div class="calendar-preview">
      <div class="overview">
        <div><span>{{ $t('importCenter.calendar.schoolYear') }}</span><strong>{{ calendar.school_year || '-' }}</strong></div>
        <div><span>{{ $t('importCenter.calendar.calendarRange') }}</span><strong>{{ calendarRange || '-' }}</strong></div>
        <div><span>{{ $t('importCenter.calendar.holidayGroups') }}</span><strong>{{ groups.length }}</strong></div>
        <div><span>{{ $t('importCenter.calendar.holidayDays') }}</span><strong>{{ selectedDateCount }}</strong></div>
      </div>

      <p v-if="summaryText" class="summary-text">{{ summaryText }}</p>
      <div v-if="summaryItems.length" class="breakdown" :aria-label="$t('importCenter.calendar.summary')">
        <span v-for="item in summaryItems" :key="item.key">{{ $t(`importCenter.calendar.${item.key}`) }} <strong>{{ item.value }}</strong></span>
      </div>

      <section class="range-section">
        <label>
          <span>{{ $t('importCenter.calendar.timetablePhase') }}</span>
          <select v-model="phase" @change="applySelectedRange">
            <option value="full_year">{{ $t('importCenter.calendar.fullYear') }}</option>
            <option value="first_term" :disabled="!ranges.first_term">{{ $t('importCenter.calendar.firstTerm') }}</option>
            <option value="second_term" :disabled="!ranges.second_term">{{ $t('importCenter.calendar.secondTerm') }}</option>
            <option value="custom">{{ $t('importCenter.calendar.customRange') }}</option>
          </select>
        </label>
        <label>
          <span>{{ $t('importCenter.startDate') }}</span>
          <input v-model="draftFrom" type="date" required @input="phase = 'custom'" />
        </label>
        <label>
          <span>{{ $t('importCenter.endDate') }}</span>
          <input v-model="draftTo" type="date" required @input="phase = 'custom'" />
        </label>
      </section>

      <section>
        <div class="section-heading">
          <div>
            <h4>{{ $t('importCenter.calendar.detectedTitle') }}</h4>
            <p>{{ $t('importCenter.calendar.detectedHint') }}</p>
          </div>
          <span>{{ $t('importCenter.calendar.selectedDays', { count: selectedDateCount }) }}</span>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">{{ $t('importCenter.calendar.include') }}</th>
                <th scope="col">{{ $t('importCenter.startDate') }}</th>
                <th scope="col">{{ $t('importCenter.endDate') }}</th>
                <th scope="col">{{ $t('importCenter.calendar.note') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="group in groups" :key="group.key" :class="{ excluded: !group.included }">
                <td><input v-model="group.included" type="checkbox" :aria-label="$t('importCenter.calendar.includeGroup', { name: group.note || group.start })" /></td>
                <td><input v-model="group.start" type="date" :min="calendarStart" :max="calendarEnd" :disabled="!group.included" /></td>
                <td><input v-model="group.end" type="date" :min="calendarStart" :max="calendarEnd" :disabled="!group.included" /></td>
                <td><input v-model="group.note" type="text" maxlength="500" :disabled="!group.included" :placeholder="$t('settings.holidays.holidayNamePlaceholder')" /></td>
              </tr>
              <tr v-if="!groups.length"><td colspan="4" class="empty">{{ $t('importCenter.calendar.noDetectedDays') }}</td></tr>
            </tbody>
          </table>
        </div>
      </section>

      <section v-if="reviewDays.length" class="review-section">
        <div class="section-heading">
          <div>
            <h4>{{ $t('importCenter.calendar.reviewTitle') }}</h4>
            <p>{{ $t('importCenter.calendar.reviewHint') }}</p>
          </div>
        </div>
        <div class="table-wrap">
          <table>
            <thead><tr><th scope="col">{{ $t('importCenter.calendar.include') }}</th><th scope="col">{{ $t('importCenter.startDate') }}</th><th scope="col">{{ $t('importCenter.endDate') }}</th><th scope="col">{{ $t('importCenter.calendar.note') }}</th></tr></thead>
            <tbody>
              <tr v-for="day in reviewDays" :key="day.key" :class="{ excluded: !day.included }">
                <td><input v-model="day.included" type="checkbox" :aria-label="$t('importCenter.calendar.includeReviewDay', { date: day.start })" /></td>
                <td><input v-model="day.start" type="date" :min="calendarStart" :max="calendarEnd" :disabled="!day.included" /></td>
                <td><input v-model="day.end" type="date" :min="calendarStart" :max="calendarEnd" :disabled="!day.included" /></td>
                <td><input v-model="day.note" type="text" maxlength="500" :disabled="!day.included" /></td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <ul v-if="warnings.length" class="warnings" role="alert">
        <li v-for="warning in warnings" :key="warning">{{ warning }}</li>
      </ul>
      <p class="merge-notice"><i class="pi pi-info-circle" aria-hidden="true"></i>{{ $t('importCenter.calendar.mergeNotice') }}</p>
      <p v-if="!canConfirm" class="invalid-range" role="alert">{{ $t('importCenter.calendar.invalidRange') }}</p>
    </div>

    <template #footer>
      <Button :label="$t('common.cancel')" text severity="secondary" @click="$emit('cancel')" />
      <Button :label="$t('importCenter.calendar.confirm')" icon="pi pi-check" :disabled="!canConfirm" @click="confirm" />
    </template>
  </Dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'

const props = defineProps({
  visible: { type: Boolean, default: false },
  calendar: { type: Object, required: true },
  effectiveFrom: { type: String, default: '' },
  effectiveTo: { type: String, default: '' },
  initialPhase: { type: String, default: 'full_year' },
})
const emit = defineEmits(['cancel', 'confirm'])

const phase = ref('full_year')
const draftFrom = ref('')
const draftTo = ref('')
const groups = ref([])
const reviewDays = ref([])

const iso = value => typeof value === 'string' ? value.slice(0, 10) : ''
const itemDate = item => iso(typeof item === 'string' ? item : item?.date || item?.data)
const itemNote = item => typeof item === 'string' ? '' : item?.note || item?.name || item?.description || ''
const datesBetween = (start, end) => {
  if (!start || !end || end < start) return []
  const dates = []
  const last = Date.parse(`${end}T00:00:00Z`)
  for (let cursor = Date.parse(`${start}T00:00:00Z`); cursor <= last && dates.length < 500; cursor += 86400000) {
    dates.push(new Date(cursor).toISOString().slice(0, 10))
  }
  return dates
}
const normalizedClosures = computed(() => (Array.isArray(props.calendar.closures) ? props.calendar.closures : [])
  .map(item => ({ ...item, date: itemDate(item), note: itemNote(item) }))
  .filter(item => item.date))
const rangeValue = value => {
  if (Array.isArray(value)) return { start: iso(value[0]), end: iso(value[1]) }
  if (!value) return null
  return {
    start: iso(value.start || value.start_date || value.effective_from),
    end: iso(value.end || value.end_date || value.effective_to),
  }
}
const ranges = computed(() => {
  const values = props.calendar.suggested_ranges || {}
  const fullYear = rangeValue(values.full_year) || {
    start: iso(props.calendar.calendar_start), end: iso(props.calendar.calendar_end),
  }
  return {
    full_year: fullYear.start && fullYear.end ? fullYear : null,
    first_term: rangeValue(values.first_term),
    second_term: rangeValue(values.second_term),
  }
})
const deriveGroups = closures => {
  const result = []
  closures.sort((left, right) => left.date.localeCompare(right.date)).forEach((closure) => {
    const previous = result.at(-1)
    const consecutive = previous && Date.parse(`${closure.date}T00:00:00Z`) - Date.parse(`${previous.end}T00:00:00Z`) === 86400000
    if (previous && previous.note === closure.note && consecutive) {
      previous.end = closure.date
      previous.originalEnd = closure.date
      previous.dates.push(closure.date)
    } else {
      result.push({
        key: `closure-${closure.date}-${result.length}`, included: true,
        start: closure.date, end: closure.date, originalStart: closure.date, originalEnd: closure.date,
        note: closure.note, dates: [closure.date],
      })
    }
  })
  return result
}
const initializeGroups = () => {
  const rawGroups = Array.isArray(props.calendar.groups)
    ? props.calendar.groups
    : Object.entries(props.calendar.groups || {}).map(([key, value]) => ({ key, ...value }))
  const mapped = rawGroups.map((group, index) => {
    const key = String(group.id ?? group.key ?? `group-${index}`)
    const start = iso(group.start || group.start_date)
    const end = iso(group.end || group.end_date || start)
    const note = group.note || group.name || group.label || ''
    const directDates = (group.dates || group.closure_dates || []).map(iso).filter(Boolean)
    const matchedDates = directDates.length ? directDates : normalizedClosures.value
      .filter(item => {
        const itemGroup = item.group_id ?? item.group_key ?? item.group
        return (itemGroup != null && String(itemGroup) === key)
          || (itemGroup == null && item.note === note && item.date >= start && item.date <= end)
      })
      .map(item => item.date)
    const dates = matchedDates.length ? [...new Set(matchedDates)].sort() : datesBetween(start, end)
    const first = start || dates[0] || ''
    const last = end || dates.at(-1) || first
    return {
      key, included: group.included !== false && group.selected !== false,
      start: first, end: last, originalStart: first, originalEnd: last, note, dates,
    }
  })
  const covered = new Set(mapped.flatMap(group => group.dates))
  groups.value = [...mapped, ...deriveGroups(normalizedClosures.value.filter(item => !covered.has(item.date)))]
}
const initialize = () => {
  initializeGroups()
  reviewDays.value = (Array.isArray(props.calendar.review_days) ? props.calendar.review_days : [])
    .map((item, index) => {
      const dates = (item?.dates || [itemDate(item)]).map(iso).filter(Boolean)
      const start = iso(item?.start || item?.start_date) || dates[0] || ''
      const end = iso(item?.end || item?.end_date) || dates.at(-1) || start
      return {
        key: `review-${start}-${index}`, included: false, start, end,
        originalStart: start, originalEnd: end, dates, note: itemNote(item),
      }
    })
    .filter(item => item.start)
  phase.value = props.effectiveFrom && props.effectiveTo ? 'custom' : props.initialPhase
  if (phase.value === 'custom') {
    draftFrom.value = props.effectiveFrom
    draftTo.value = props.effectiveTo
  } else applySelectedRange()
}
watch(() => props.calendar, initialize, { immediate: true })

const groupDates = group => group.start === group.originalStart && group.end === group.originalEnd && group.dates.length
  ? group.dates.filter(date => date >= group.start && date <= group.end)
  : datesBetween(group.start, group.end)
const selectedClosures = computed(() => {
  const byDate = new Map()
  groups.value.filter(group => group.included).forEach(group => groupDates(group).forEach(date => {
    byDate.set(date, { date, note: group.note.trim() || null })
  }))
  reviewDays.value.filter(day => day.included).forEach(day => groupDates(day).forEach(date => {
    byDate.set(date, { date, note: day.note.trim() || null })
  }))
  return [...byDate.values()].sort((left, right) => left.date.localeCompare(right.date))
})
const selectedDateCount = computed(() => selectedClosures.value.length)
const calendarStart = computed(() => iso(props.calendar.calendar_start))
const calendarEnd = computed(() => iso(props.calendar.calendar_end))
const invalidGroup = computed(() => [...groups.value, ...reviewDays.value]
  .some(group => group.included && (!group.start || !group.end || group.end < group.start
    || group.start < calendarStart.value || group.end > calendarEnd.value)))
const canConfirm = computed(() => draftFrom.value && draftTo.value && draftTo.value >= draftFrom.value && !invalidGroup.value)
const calendarRange = computed(() => [calendarStart.value, calendarEnd.value].filter(Boolean).join(' – '))
const summaryText = computed(() => {
  const summary = props.calendar.summary
  if (typeof summary === 'string') return summary
  if (Array.isArray(summary)) return summary.join('；')
  return summary?.note || summary?.description || ''
})
const summaryItems = computed(() => [
  ['schoolHolidayDays', props.calendar.summary?.school_holiday_days],
  ['selfDecidedDays', props.calendar.summary?.self_decided_days],
  ['teacherDevelopmentDays', props.calendar.summary?.teacher_development_days],
].filter(([, value]) => value != null).map(([key, value]) => ({ key, value })))
const warnings = computed(() => (Array.isArray(props.calendar.warnings) ? props.calendar.warnings : [])
  .map(item => typeof item === 'string' ? item : item?.message)
  .filter(Boolean))

function applySelectedRange() {
  if (phase.value === 'custom') return
  const range = ranges.value[phase.value]
  if (!range) return
  draftFrom.value = range.start
  draftTo.value = range.end
}
const onVisibilityChange = value => { if (!value) emit('cancel') }
const confirm = () => {
  if (!canConfirm.value) return
  emit('confirm', {
    phase: phase.value,
    effective_from: draftFrom.value,
    effective_to: draftTo.value,
    calendar_closures: selectedClosures.value,
  })
}
</script>

<style scoped>
.calendar-preview { display: grid; gap: 1rem; color: var(--text-color-primary); }
.overview { display: grid; grid-template-columns: repeat(4, 1fr); overflow: hidden; border: 1px solid var(--border-color); border-radius: 10px; }
.overview div { display: grid; gap: .2rem; padding: .7rem .8rem; border-left: 1px solid var(--border-color); }
.overview div:first-child { border-left: 0; }
.overview span, .section-heading p { color: var(--text-color-secondary); font-size: var(--font-supporting); }
.overview strong { font-size: var(--font-data); font-variant-numeric: tabular-nums; }
.summary-text { margin: 0; color: var(--text-color-secondary); font-size: var(--font-ui); }
.breakdown { display: flex; flex-wrap: wrap; gap: .4rem; }
.breakdown span { padding: .3rem .55rem; border-radius: 999px; background: var(--surface-soft); color: var(--text-color-secondary); font-size: var(--font-supporting); }
.breakdown strong { color: var(--text-color-primary); }
.range-section { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: .75rem; padding: .8rem; border-radius: 9px; background: var(--surface-soft); }
label { display: grid; gap: .3rem; color: #344054; font-size: var(--font-ui); font-weight: 650; }
input, select { width: 100%; min-height: 2.45rem; padding: .52rem .6rem; border: 1px solid #cfd6df; border-radius: 8px; background: #fff; color: var(--text-color-primary); }
input[type=checkbox] { width: auto; min-height: auto; accent-color: var(--primary-color); }
.section-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: .75rem; margin-bottom: .55rem; }
.section-heading h4, .section-heading p { margin: 0; }
.section-heading p { margin-top: .2rem; }
.section-heading > span { color: var(--text-color-secondary); font-size: var(--font-supporting); white-space: nowrap; }
.table-wrap { overflow: auto; border: 1px solid var(--border-color); border-radius: 9px; }
table { width: 100%; border-collapse: collapse; font-size: var(--font-data); }
th, td { padding: .48rem .55rem; border-bottom: 1px solid #edf0f3; text-align: left; }
th { background: var(--surface-soft); color: var(--text-color-secondary); font-size: var(--font-supporting); }
th:first-child, td:first-child { width: 4.5rem; text-align: center; }
td:nth-child(2), td:nth-child(3) { width: 10.5rem; }
tbody tr:last-child td { border-bottom: 0; }
tr.excluded { opacity: .52; }
td input { min-width: 9rem; }
.empty { padding: 1rem; color: var(--text-color-secondary); text-align: center; }
.review-section { padding-top: .15rem; }
.warnings { margin: 0; padding: .7rem .8rem .7rem 1.8rem; border-left: 3px solid #b77816; border-radius: 8px; background: #fff8e8; color: #805515; font-size: var(--font-ui); }
.merge-notice { display: flex; align-items: center; gap: .45rem; margin: 0; padding: .7rem .8rem; border-radius: 8px; background: #eef5ff; color: #345f8c; font-size: var(--font-ui); }
.invalid-range { margin: 0; color: #96382f; font-size: var(--font-ui); }
@media (max-width: 720px) {
  .overview { grid-template-columns: 1fr 1fr; }
  .overview div:nth-child(3) { border-top: 1px solid var(--border-color); border-left: 0; }
  .overview div:nth-child(4) { border-top: 1px solid var(--border-color); }
  .range-section { grid-template-columns: 1fr; }
}
</style>
