<template>
  <div class="holiday-settings">
    <div class="section-heading">
      <div><h3>{{ $t('settings.holidays.title') }}</h3><p>{{ $t('settings.holidays.hint') }}</p></div>
      <label>{{ $t('settings.holidays.course') }}
        <select v-model.number="courseId" :disabled="!cursos.length">
          <option v-if="!cursos.length" :value="null">{{ $t('settings.holidays.needCourse') }}</option>
          <option v-for="item in cursos" :key="item.id" :value="item.id">{{ item.nom }}</option>
        </select>
      </label>
    </div>

    <p v-if="course && !course.data_fi" class="notice">{{ $t('settings.holidays.completeCourse') }}</p>
    <template v-else-if="course">
      <div class="mode-switch" role="group" :aria-label="$t('settings.holidays.method')">
        <button type="button" :class="{ active: mode === 'text' }" @click="mode = 'text'">{{ $t('settings.holidays.textMethod') }}</button>
        <button type="button" :class="{ active: mode === 'calendar' }" @click="mode = 'calendar'">{{ $t('settings.holidays.calendarMethod') }}</button>
      </div>

      <div v-if="mode === 'text'" class="text-import">
        <label>{{ $t('settings.holidays.textLabel') }}
          <textarea v-model="textDates" rows="7" :placeholder="$t('settings.holidays.textPlaceholder')"></textarea>
        </label>
        <Button :label="$t('settings.holidays.importDates')" icon="pi pi-download" outlined @click="importTextDates" />
      </div>

      <div v-else class="year-calendar">
        <article v-for="month in months" :key="month.key" class="month-card">
          <h4>{{ month.label }}</h4>
          <div class="month-grid weekday-row"><span v-for="day in weekdayLabels" :key="day">{{ day }}</span></div>
          <div class="month-grid">
            <span v-for="blank in month.leading" :key="`blank-${blank}`"></span>
            <button
              v-for="day in month.days"
              :key="day.iso"
              type="button"
              :class="{ selected: selectedDates.has(day.iso), weekend: day.weekend }"
              :aria-pressed="selectedDates.has(day.iso)"
              :aria-label="day.iso"
              @click="toggleDate(day.iso)"
            >{{ day.day }}</button>
          </div>
        </article>
      </div>

      <p v-if="message" :class="['feedback', { error: hasError }]">{{ message }}</p>
      <div class="save-row">
        <span>{{ $t('settings.holidays.selected', { count: selectedDates.size }) }}</span>
        <Button :label="$t('settings.holidays.clear')" text severity="secondary" @click="clearDates" />
        <Button :label="$t('common.save')" icon="pi pi-save" :loading="busy" @click="save" />
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import axios from 'axios'
import Button from 'primevue/button'
import { useCursos } from './useCursos.js'

const { t, locale } = useI18n()
const { cursos } = useCursos()
const courseId = ref(null)
const mode = ref('text')
const textDates = ref('')
const selectedDates = ref(new Set())
const allClosures = ref([])
const busy = ref(false)
const message = ref('')
const hasError = ref(false)

const course = computed(() => cursos.value.find(item => item.id === courseId.value) || null)
const weekdayLabels = computed(() => Array.from({ length: 7 }, (_, index) => t(`settings.holidays.weekdays.${index}`)))
const toDate = (value) => {
  const [year, month, day] = value.split('-').map(Number)
  return new Date(year, month - 1, day, 12)
}
const toIso = (value) => {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}
const months = computed(() => {
  if (!course.value?.data_fi) return []
  const start = toDate(course.value.data_inici)
  const end = toDate(course.value.data_fi)
  const result = []
  for (let cursor = new Date(start.getFullYear(), start.getMonth(), 1, 12); cursor <= end; cursor.setMonth(cursor.getMonth() + 1)) {
    const year = cursor.getFullYear()
    const month = cursor.getMonth()
    const daysInMonth = new Date(year, month + 1, 0, 12).getDate()
    const days = Array.from({ length: daysInMonth }, (_, index) => {
      const value = new Date(year, month, index + 1, 12)
      return { day: index + 1, iso: toIso(value), weekend: value.getDay() === 0 || value.getDay() === 6 }
    }).filter(item => item.iso >= course.value.data_inici && item.iso <= course.value.data_fi)
    const firstDay = days.length ? toDate(days[0].iso) : cursor
    result.push({
      key: `${year}-${month + 1}`,
      label: new Intl.DateTimeFormat(locale.value === 'en' ? 'en-HK' : 'zh-HK', { year: 'numeric', month: 'long' }).format(cursor),
      leading: (firstDay.getDay() + 6) % 7,
      days,
    })
  }
  return result
})

const loadCourseDates = () => {
  if (!course.value?.data_fi) return selectedDates.value = new Set()
  selectedDates.value = new Set(allClosures.value
    .map(item => item.date)
    .filter(value => value >= course.value.data_inici && value <= course.value.data_fi))
  message.value = ''
}
watch(cursos, values => {
  if (!values.some(item => item.id === courseId.value)) courseId.value = values[0]?.id || null
}, { immediate: true })
watch(courseId, loadCourseDates)

const toggleDate = (value) => {
  const next = new Set(selectedDates.value)
  next.has(value) ? next.delete(value) : next.add(value)
  selectedDates.value = next
  message.value = ''
}
const clearDates = () => {
  selectedDates.value = new Set()
  message.value = ''
}
const importTextDates = () => {
  const tokens = textDates.value.trim().split(/[\s,，;；]+/).filter(Boolean)
  const next = new Set(selectedDates.value)
  for (const token of tokens) {
    const match = /^(\d{4})\/(\d{2})\/(\d{2})$/.exec(token)
    if (!match) return showError(t('settings.holidays.invalidDate', { date: token }))
    const iso = `${match[1]}-${match[2]}-${match[3]}`
    if (toIso(toDate(iso)) !== iso) return showError(t('settings.holidays.invalidDate', { date: token }))
    if (iso < course.value.data_inici || iso > course.value.data_fi) return showError(t('settings.holidays.outOfRange', { date: token }))
    next.add(iso)
  }
  selectedDates.value = next
  hasError.value = false
  message.value = t('settings.holidays.imported', { count: tokens.length })
}
const showError = (value) => {
  hasError.value = true
  message.value = value
}
const save = async () => {
  busy.value = true
  message.value = ''
  try {
    const notes = new Map(allClosures.value.map(item => [item.date, item.note]))
    const closures = [...selectedDates.value].sort().map(data => ({ data, note: notes.get(data) || null }))
    await axios.put('/api/calendar/closures', { course_id: courseId.value, closures })
    allClosures.value = [
      ...allClosures.value.filter(item => item.date < course.value.data_inici || item.date > course.value.data_fi),
      ...closures.map(item => ({ date: item.data, note: item.note })),
    ]
    hasError.value = false
    message.value = t('settings.holidays.saved')
  } finally { busy.value = false }
}

onMounted(async () => {
  allClosures.value = (await axios.get('/api/calendar/closures')).data
  loadCourseDates()
})
</script>

<style scoped>
.holiday-settings { display: grid; gap: 1rem; }
.section-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 1rem; }
h3, h4 { margin: 0; }
.section-heading p { margin: .3rem 0 0; color: var(--text-color-secondary); }
label { display: flex; flex-direction: column; gap: .35rem; color: #344054; font-size: .84rem; font-weight: 650; }
select, textarea { min-height: 2.5rem; padding: .55rem .65rem; border: 1px solid #cfd6df; border-radius: 8px; background: #fff; color: var(--text-color-primary); }
textarea { width: 100%; resize: vertical; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; }
.notice { padding: 1rem; border-radius: 8px; background: #fff8e8; color: #8a5b16; }
.mode-switch { display: inline-flex; width: fit-content; padding: .2rem; border-radius: 8px; background: var(--surface-soft); }
.mode-switch button { padding: .48rem .75rem; border: 0; border-radius: 6px; background: transparent; color: var(--text-color-secondary); cursor: pointer; font-weight: 650; }
.mode-switch button.active { background: #fff; color: var(--primary-color-dark); box-shadow: 0 1px 3px rgba(28, 45, 78, .12); }
.text-import { display: grid; gap: .75rem; }
.text-import .p-button { justify-self: end; }
.year-calendar { display: grid; grid-template-columns: repeat(3, minmax(210px, 1fr)); gap: .75rem; }
.month-card { padding: .75rem; border: 1px solid var(--border-color); border-radius: 9px; }
.month-card h4 { margin-bottom: .5rem; text-align: center; font-size: .88rem; }
.month-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: .18rem; }
.weekday-row { margin-bottom: .2rem; color: var(--text-color-secondary); font-size: .68rem; text-align: center; }
.month-grid button { aspect-ratio: 1; border: 0; border-radius: 5px; background: transparent; color: var(--text-color-primary); cursor: pointer; }
.month-grid button:hover { background: var(--surface-soft); }
.month-grid button.weekend { color: #9a6670; }
.month-grid button.selected { background: var(--primary-color); color: #fff; font-weight: 700; }
.feedback { margin: 0; color: #216a42; font-size: .84rem; }
.feedback.error { color: #9b3b30; }
.save-row { display: flex; align-items: center; justify-content: flex-end; gap: .5rem; color: var(--text-color-secondary); font-size: .82rem; }
@media (max-width: 800px) { .year-calendar { grid-template-columns: repeat(2, minmax(200px, 1fr)); } }
@media (max-width: 560px) { .section-heading, .save-row { align-items: stretch; flex-direction: column; } .year-calendar { grid-template-columns: 1fr; } }
</style>
