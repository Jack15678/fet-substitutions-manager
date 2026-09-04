<template>
  <Dialog
    :visible="visible"
    class="calendar-review-dialog"
    modal
    :header="$t('importCenter.calendar.dialogTitle')"
    :style="{ width: 'min(96vw, 1120px)' }"
    :content-style="{ maxHeight: '78vh', overflow: 'auto' }"
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
                <th scope="col">
                  <label class="select-all">
                    <input
                      type="checkbox"
                      :checked="allGroupsIncluded"
                      :indeterminate="someGroupsIncluded && !allGroupsIncluded"
                      @change="toggleAllGroups"
                    />
                    <span>{{ $t('importCenter.calendar.include') }}</span>
                  </label>
                </th>
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
      <Button class="calendar-cancel" :label="$t('common.cancel')" outlined severity="secondary" @click="$emit('cancel')" />
      <Button class="calendar-confirm" :label="$t('importCenter.calendar.confirm')" icon="pi pi-check" :disabled="!canConfirm" @click="confirm" />
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
const allGroupsIncluded = computed(() => groups.value.length > 0 && groups.value.every(group => group.included))
const someGroupsIncluded = computed(() => groups.value.some(group => group.included))
const calendarStart = computed(() => iso(props.calendar.calendar_start))
const calendarEnd = computed(() => iso(props.calendar.calendar_end))
const invalidGroup = computed(() => [...groups.value, ...reviewDays.value]
  .some(group => group.included && (!group.start || !group.end || group.end < group.start
    || group.start < calendarStart.value || group.end > calendarEnd.value)))
const canConfirm = computed(() => draftFrom.value && draftTo.value && draftTo.value >= draftFrom.value && !invalidGroup.value)
const calendarRange = computed(() => [calendarStart.value, calendarEnd.value].filter(Boolean).join(' - '))
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
const toggleAllGroups = event => groups.value.forEach(group => { group.included = event.target.checked })
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
:global(.calendar-review-dialog) {
  overflow: hidden;
  border: 0;
  border-radius: 8px;
  box-shadow: 0 24px 72px rgba(12, 47, 85, .2);
}

:global(.calendar-review-dialog .p-dialog-header) {
  padding: 1.15rem 1.45rem;
  border-bottom: 0;
  background: #0c3158;
  color: #fff;
}

:global(.calendar-review-dialog .p-dialog-title) {
  font-size: clamp(1.25rem, 2vw, 1.55rem);
  font-weight: 750;
  letter-spacing: -.025em;
}

:global(.calendar-review-dialog .p-dialog-header-icon) {
  width: 2.35rem;
  height: 2.35rem;
  color: #fff;
  transition: background-color var(--motion-fast) var(--motion-ease), transform var(--motion-fast) var(--motion-ease);
}

:global(.calendar-review-dialog .p-dialog-header-icon:hover) {
  background: rgba(255, 255, 255, .12);
  color: #fff;
}

:global(.calendar-review-dialog .p-dialog-header-icon:active) { transform: translateY(1px); }
:global(.calendar-review-dialog .p-dialog-header-icon:focus-visible) { box-shadow: 0 0 0 3px rgba(255, 255, 255, .35); }

:global(.calendar-review-dialog .p-dialog-content) {
  padding: 1.2rem 1.45rem 1.35rem;
  background: #fff;
  color: var(--text-color-primary);
}

:global(.calendar-review-dialog .p-dialog-footer) {
  display: flex;
  justify-content: flex-end;
  gap: .7rem;
  padding: .9rem 1.45rem 1rem;
  border-top: 1px solid var(--border-color);
  background: #fbfcfd;
}

.calendar-preview { display: grid; gap: 1rem; color: var(--text-color-primary); }

.overview {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  padding: .05rem 0 .9rem;
  border-bottom: 1px solid var(--border-color);
}

.overview div {
  display: flex;
  align-items: baseline;
  gap: .45rem;
  min-width: 0;
  padding: 0 1.1rem;
  border-left: 1px solid var(--border-strong);
}

.overview div:first-child { padding-left: 0; border-left: 0; }
.overview span, .section-heading p { color: var(--text-color-secondary); font-size: var(--font-supporting); }
.overview strong { color: var(--text-color-primary); font-size: var(--font-critical); font-variant-numeric: tabular-nums; }
.summary-text { margin: -.25rem 0 0; color: var(--text-color-secondary); font-size: var(--font-ui); }

.breakdown {
  display: flex;
  flex-wrap: wrap;
  gap: 1.75rem;
  margin-top: -.35rem;
  padding: 0 .15rem .65rem;
  border-bottom: 1px solid var(--border-color);
}

.breakdown span { color: var(--text-color-secondary); font-size: var(--font-ui); }
.breakdown strong { color: var(--primary-color-dark); font-variant-numeric: tabular-nums; }

.range-section {
  display: grid;
  grid-template-columns: 1.05fr 1fr 1fr;
  gap: 1.2rem;
  padding: .25rem 0 1rem;
  border-bottom: 1px solid var(--border-color);
}

label { color: #344054; font-size: var(--font-ui); font-weight: 650; }
.range-section label { display: flex; align-items: center; gap: .65rem; min-width: 0; }
.range-section label > span { flex: 0 0 auto; white-space: nowrap; }

.calendar-preview input:not([type=checkbox]),
.calendar-preview select {
  width: 100%;
  min-width: 0;
  min-height: 2.45rem;
  padding: .48rem .65rem;
  border: 1px solid #cbd6df;
  border-radius: 6px;
  background: #fff;
  color: var(--text-color-primary);
  font-variant-numeric: tabular-nums;
  transition: border-color var(--motion-fast) var(--motion-ease), box-shadow var(--motion-fast) var(--motion-ease), background-color var(--motion-fast) var(--motion-ease);
}

.calendar-preview input:not([type=checkbox]):hover,
.calendar-preview select:hover { border-color: #9fb0bf; }
.calendar-preview input:not([type=checkbox]):focus,
.calendar-preview select:focus { border-color: var(--primary-color); }
.calendar-preview input[type=checkbox] { width: 1.05rem; height: 1.05rem; accent-color: #135da5; }

.section-heading { display: flex; align-items: baseline; justify-content: space-between; gap: 1rem; margin-bottom: .6rem; }
.section-heading > div { display: flex; flex-wrap: wrap; align-items: baseline; gap: .75rem; min-width: 0; }
.section-heading h4, .section-heading p { margin: 0; }
.section-heading h4 { color: var(--primary-color-dark); font-size: var(--font-critical); letter-spacing: -.01em; }
.section-heading > span { color: #135da5; font-size: var(--font-ui); font-weight: 700; white-space: nowrap; }

.table-wrap {
  max-height: min(42vh, 27rem);
  overflow: auto;
  border: 1px solid var(--border-strong);
  border-radius: 6px;
}

table { width: 100%; min-width: 760px; border-collapse: collapse; font-size: var(--font-data); font-variant-numeric: tabular-nums; }
th, td { height: 3.5rem; padding: .45rem .75rem; border-right: 1px solid #e3e8ec; border-bottom: 1px solid #e3e8ec; text-align: left; }
th:last-child, td:last-child { border-right: 0; }

th {
  position: sticky;
  z-index: 1;
  top: 0;
  background: #f1f4f6;
  color: #344657;
  font-size: var(--font-ui);
  font-weight: 700;
}

th:first-child, td:first-child { width: 6rem; text-align: center; }
td:nth-child(2), td:nth-child(3) { width: 11.5rem; }
tbody tr { background: #f8fbfe; transition: background-color var(--motion-fast) var(--motion-ease); }
tbody tr:hover:not(.excluded) { background: #edf5fb; }
tbody tr:last-child td { border-bottom: 0; }
tr.excluded { background: #fff; color: var(--text-color-secondary); }
tr.excluded input:not([type=checkbox]) { background: #f5f7f8; }
td input { min-width: 9rem; }
.select-all { display: inline-flex; align-items: center; justify-content: center; gap: .45rem; cursor: pointer; }
.empty { padding: 1rem; color: var(--text-color-secondary); text-align: center; }
.review-section { padding-top: .15rem; }
.warnings { margin: 0; padding: .7rem .8rem .7rem 1.8rem; border-left: 3px solid #b77816; border-radius: 6px; background: #fff8e8; color: #805515; font-size: var(--font-ui); }
.merge-notice { display: flex; align-items: center; gap: .45rem; margin: 0; padding: .7rem .8rem; border-radius: 6px; background: #eef5fb; color: #345f8c; font-size: var(--font-ui); }
.invalid-range { margin: 0; color: #96382f; font-size: var(--font-ui); }

.calendar-cancel,
.calendar-confirm { min-height: 2.7rem; border-radius: 6px; font-weight: 700; transition: transform var(--motion-fast) var(--motion-ease), border-color var(--motion-fast) var(--motion-ease), background-color var(--motion-fast) var(--motion-ease); }
.calendar-cancel { min-width: 6.25rem; background: #fff; }
.calendar-confirm { min-width: 10.5rem; border-color: #0756b3; background: #0756b3; }
.calendar-confirm:hover:not(:disabled) { border-color: #06478f; background: #06478f; }
.calendar-cancel:active,
.calendar-confirm:active:not(:disabled) { transform: translateY(1px); }

@media (max-width: 900px) {
  .range-section { grid-template-columns: 1fr; gap: .65rem; }
  .range-section label { display: grid; grid-template-columns: 8.5rem minmax(0, 1fr); }
}

@media (max-width: 720px) {
  :global(.calendar-review-dialog) { border-radius: 0; }
  :global(.calendar-review-dialog .p-dialog-header),
  :global(.calendar-review-dialog .p-dialog-content),
  :global(.calendar-review-dialog .p-dialog-footer) { padding-right: 1rem; padding-left: 1rem; }
  .overview { display: grid; grid-template-columns: 1fr 1fr; gap: .75rem 1rem; }
  .overview div, .overview div:first-child { display: grid; gap: .15rem; padding: 0; border: 0; }
  .breakdown { flex-wrap: nowrap; gap: 1.25rem; overflow-x: auto; white-space: nowrap; }
  .range-section label { grid-template-columns: 1fr; gap: .3rem; }
  .section-heading { align-items: flex-start; flex-direction: column; gap: .35rem; }
  .section-heading > div { display: grid; gap: .2rem; }
  .table-wrap { max-height: 48vh; }
  .calendar-cancel, .calendar-confirm { flex: 1; min-width: 0; }
}

@media (prefers-reduced-motion: reduce) {
  :global(.calendar-review-dialog .p-dialog-header-icon),
  .calendar-preview input,
  .calendar-preview select,
  tbody tr,
  .calendar-cancel,
  .calendar-confirm { transition: none; }
}
</style>
