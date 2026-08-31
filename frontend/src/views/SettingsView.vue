<template>
  <section class="settings-page">
    <header class="page-heading">
      <h2>{{ $t('settings.title') }}</h2>
      <p>{{ $t('settings.description') }}</p>
    </header>

    <section class="panel">
      <HolidaySettings />
    </section>

    <section class="panel">
      <div><h3>{{ $t('settings.periodTitle') }}</h3><p>{{ $t('settings.periodHint') }}</p></div>
      <form @submit.prevent="savePeriods">
        <label class="cycle-setting">
          <span><b>{{ $t('settings.maxCycleLessons') }}</b><small>{{ $t('settings.maxCycleHint') }}</small></span>
          <input v-model.number="maxCycleLessons" type="number" min="2" max="5" required />
        </label>
        <div v-for="item in periods" :key="item.period" class="period-row">
          <b>{{ $t('records.period', { period: item.period }) }}</b>
          <input v-model="item.start" type="time" required />
          <span>→</span>
          <input v-model="item.end" type="time" required />
        </div>
        <div class="save-row">
          <Transition name="motion-fade"><span v-if="saved">{{ $t('common.saved') }}</span></Transition>
          <Button type="submit" :label="$t('common.save')" icon="pi pi-save" :loading="busy" />
        </div>
      </form>
    </section>
  </section>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import axios from 'axios'
import Button from 'primevue/button'
import HolidaySettings from '../components/config/HolidaySettings.vue'

const periods = ref([])
const maxCycleLessons = ref(3)
const busy = ref(false)
const saved = ref(false)

const savePeriods = async () => {
  busy.value = true
  saved.value = false
  try {
    await axios.put('/api/rescheduling/config', { max_cycle_lessons: maxCycleLessons.value })
    const periodResponse = await axios.put('/api/rescheduling/period-times', { periods: periods.value })
    periods.value = periodResponse.data.periods
    saved.value = true
  } finally { busy.value = false }
}

onMounted(async () => {
  const [periodResponse, configResponse] = await Promise.all([
    axios.get('/api/rescheduling/period-times'), axios.get('/api/rescheduling/config')
  ])
  periods.value = periodResponse.data.periods
  maxCycleLessons.value = configResponse.data.max_cycle_lessons
})
</script>

<style scoped>
.settings-page { display: grid; gap: 1.25rem; color: var(--text-color-primary); }
.page-heading h2, h3 { margin: 0; }
.page-heading h2 { font-size: clamp(1.65rem, 3vw, 2.15rem); letter-spacing: -.035em; }
.page-heading p, .panel p { margin-top: .3rem; color: var(--text-color-secondary); }
.panel { width: 100%; padding: 1.25rem; border: 1px solid var(--border-color); border-radius: var(--radius-lg); background: var(--card-background); box-shadow: var(--shadow-panel); }
form { display: grid; gap: .45rem; margin-top: 1rem; }
.period-row { display: grid; grid-template-columns: 82px 1fr auto 1fr; align-items: center; gap: .55rem; }
.period-row b { font-size: var(--font-data); }
input { min-height: 2.5rem; padding: .55rem .65rem; border: 1px solid #cfd6df; border-radius: 8px; background: #fff; color: var(--text-color-primary); }
.cycle-setting { display: flex; align-items: center; justify-content: space-between; gap: 1rem; margin-bottom: .65rem; padding-bottom: 1rem; border-bottom: 1px solid var(--border-color); }
.cycle-setting span { display: flex; flex-direction: column; gap: .2rem; }
.cycle-setting small { color: var(--text-color-secondary); }
.cycle-setting input { width: 90px; }
.save-row { display: flex; align-items: center; justify-content: flex-end; gap: .6rem; margin-top: .45rem; color: #216a42; font-size: var(--font-supporting); }
@media (max-width: 600px) { .period-row { grid-template-columns: 72px 1fr auto 1fr; gap: .35rem; } .panel { padding: 1rem; } }
</style>
