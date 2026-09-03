<template>
  <div class="holiday-settings">
    <div class="section-heading">
      <div><h3>{{ $t('settings.holidays.title') }}</h3><p>{{ $t('settings.holidays.hint') }}</p></div>
      <label>{{ $t('settings.holidays.year') }}
        <input v-model.number="year" type="number" min="1900" max="2100" @change="loadYearDates" />
      </label>
    </div>

    <div class="holiday-editor">
      <div class="year-calendar">
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

      <aside class="holiday-notes">
        <h4>{{ $t('settings.holidays.selectedHolidays') }}</h4>
        <p v-if="!selectedDatesSorted.length">{{ $t('settings.holidays.noSelectedHolidays') }}</p>
        <label v-for="date in selectedDatesSorted" :key="date">
          <span>{{ date.replaceAll('-', '/') }}</span>
          <input v-model="closureNotes[date]" type="text" :placeholder="$t('settings.holidays.holidayNamePlaceholder')" />
        </label>
      </aside>
    </div>

    <Transition name="motion-fade"><p v-if="message" :class="['feedback', { error: hasError }]" :role="hasError ? 'alert' : undefined">{{ message }}</p></Transition>
    <div class="save-row">
      <span>{{ $t('settings.holidays.selected', { count: selectedDates.size }) }}</span>
      <Button :label="$t('settings.holidays.clear')" text severity="secondary" @click="clearDates" />
      <Button :label="$t('common.save')" icon="pi pi-save" :loading="busy" @click="save" />
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import axios from 'axios'
import Button from 'primevue/button'

const { t, locale } = useI18n()
const year = ref(new Date().getFullYear())
const selectedDates = ref(new Set())
const closureNotes = ref({})
const allClosures = ref([])
const busy = ref(false)
const message = ref('')
const hasError = ref(false)

const weekdayLabels = computed(() => Array.from({ length: 7 }, (_, index) => t(`settings.holidays.weekdays.${index}`)))
const selectedDatesSorted = computed(() => [...selectedDates.value].sort())
const toIso = (value) => {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}
const months = computed(() => {
  if (!Number.isInteger(year.value) || year.value < 1900 || year.value > 2100) return []
  const result = []
  for (let month = 0; month < 12; month += 1) {
    const cursor = new Date(year.value, month, 1, 12)
    const daysInMonth = new Date(year.value, month + 1, 0, 12).getDate()
    const days = Array.from({ length: daysInMonth }, (_, index) => {
      const value = new Date(year.value, month, index + 1, 12)
      return { day: index + 1, iso: toIso(value), weekend: value.getDay() === 0 || value.getDay() === 6 }
    })
    result.push({
      key: `${year.value}-${month + 1}`,
      label: new Intl.DateTimeFormat(locale.value === 'en' ? 'en-HK' : 'zh-HK', { year: 'numeric', month: 'long' }).format(cursor),
      leading: (cursor.getDay() + 6) % 7,
      days,
    })
  }
  return result
})

const loadYearDates = () => {
  const closures = allClosures.value.filter(item => item.date.startsWith(`${year.value}-`))
  selectedDates.value = new Set(closures.map(item => item.date))
  closureNotes.value = Object.fromEntries(closures.map(item => [item.date, item.note || '']))
  message.value = ''
}
watch(year, loadYearDates)

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
const showError = (value) => {
  hasError.value = true
  message.value = value
}
const save = async () => {
  busy.value = true
  message.value = ''
  try {
    const closures = selectedDatesSorted.value.map(data => ({ data, note: closureNotes.value[data]?.trim() || null }))
    await axios.put('/api/calendar/closures', { year: year.value, closures })
    allClosures.value = [
      ...allClosures.value.filter(item => !item.date.startsWith(`${year.value}-`)),
      ...closures.map(item => ({ date: item.data, note: item.note })),
    ]
    hasError.value = false
    message.value = t('settings.holidays.saved')
  } catch (requestError) {
    showError(requestError.response?.data?.detail || t('settings.holidays.saveError'))
  } finally { busy.value = false }
}

onMounted(async () => {
  try {
    allClosures.value = (await axios.get('/api/calendar/closures')).data
    loadYearDates()
  } catch (requestError) {
    showError(requestError.response?.data?.detail || t('settings.holidays.loadError'))
  }
})
</script>

<style scoped>
.holiday-settings { display: grid; gap: 1rem; }
.section-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 1rem; }
h3, h4 { margin: 0; }
.section-heading p { margin: .3rem 0 0; color: var(--text-color-secondary); }
label { display: flex; flex-direction: column; gap: .35rem; color: #344054; font-size: var(--font-ui); font-weight: 650; }
input { min-height: 2.5rem; padding: .55rem .65rem; border: 1px solid #cfd6df; border-radius: 8px; background: #fff; color: var(--text-color-primary); }
.holiday-editor { display: grid; grid-template-columns: minmax(0, 1fr) 280px; gap: 1rem; align-items: start; }
.year-calendar { display: grid; grid-template-columns: repeat(3, minmax(210px, 1fr)); gap: .75rem; }
.month-card { padding: .75rem; border: 1px solid var(--border-color); border-radius: 9px; }
.month-card h4 { margin-bottom: .5rem; text-align: center; font-size: var(--font-data); }
.month-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: .18rem; }
.weekday-row { margin-bottom: .2rem; color: var(--text-color-secondary); font-size: var(--font-supporting); text-align: center; }
.month-grid button { aspect-ratio: 1; border: 0; border-radius: 5px; background: transparent; color: var(--text-color-primary); cursor: pointer; transition: background-color var(--motion-fast) var(--motion-ease), color var(--motion-fast) var(--motion-ease), transform var(--motion-fast) var(--motion-ease); }
.month-grid button:active { transform: scale(.9); }
.month-grid button:hover { background: var(--surface-soft); }
.month-grid button.weekend { color: #9a6670; }
.month-grid button.selected { background: var(--primary-color); color: #fff; font-weight: 700; }
.holiday-notes { display: grid; gap: .75rem; padding: .9rem; border: 1px solid var(--border-color); border-radius: 9px; }
.holiday-notes > p { margin: 0; color: var(--text-color-secondary); font-size: var(--font-ui); }
.holiday-notes label span { font-variant-numeric: tabular-nums; }
.feedback { margin: 0; color: #216a42; font-size: var(--font-ui); }
.feedback.error { color: #9b3b30; }
.save-row { display: flex; align-items: center; justify-content: flex-end; gap: .5rem; color: var(--text-color-secondary); font-size: var(--font-ui); }
@media (max-width: 1050px) { .holiday-editor { grid-template-columns: 1fr; } }
@media (max-width: 800px) { .year-calendar { grid-template-columns: repeat(2, minmax(200px, 1fr)); } }
@media (max-width: 560px) { .section-heading, .save-row { align-items: stretch; flex-direction: column; } .year-calendar { grid-template-columns: 1fr; } }
</style>
