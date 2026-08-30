<template>
  <details class="daily-export">
    <summary>
      <i class="pi pi-download" aria-hidden="true"></i>
      {{ $t('dailyExport.title') }}
    </summary>
    <form class="export-panel" @submit.prevent>
      <p>{{ $t('dailyExport.hint') }}</p>
      <label for="daily-export-date">
        <span>{{ $t('dailyExport.date') }}</span>
        <input id="daily-export-date" v-model="exportDate" type="date" required />
      </label>
      <div class="actions">
        <Button
          :label="$t('dailyExport.excel')"
          icon="pi pi-file-excel"
          :loading="busy === 'xlsx'"
          :disabled="!exportDate || !!busy"
          @click="download('xlsx')"
        />
        <Button
          :label="$t('dailyExport.pdf')"
          icon="pi pi-file-pdf"
          severity="danger"
          :loading="busy === 'pdf'"
          :disabled="!exportDate || !!busy"
          @click="download('pdf')"
        />
      </div>
    </form>
  </details>
</template>

<script setup>
import { ref, watch } from 'vue'
import axios from 'axios'
import Button from 'primevue/button'

const props = defineProps({ date: { type: Date, default: null } })
const iso = (value) => {
  const date = value || new Date()
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000)
  return local.toISOString().slice(0, 10)
}
const exportDate = ref(iso(props.date))
const busy = ref('')

watch(() => props.date, value => { exportDate.value = iso(value) })

const download = async (format) => {
  busy.value = format
  try {
    const response = await axios.get(`/api/rescheduling/exports/daily.${format}`, {
      params: { data: exportDate.value },
      responseType: 'blob'
    })
    const disposition = response.headers['content-disposition'] || ''
    const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1]
      || `daily-substitution-${exportDate.value}.${format}`
    const url = URL.createObjectURL(response.data)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    link.click()
    URL.revokeObjectURL(url)
  } finally {
    busy.value = ''
  }
}
</script>

<style scoped>
.daily-export { position: relative; color: var(--text-color-primary); }
summary {
  display: flex;
  align-items: center;
  gap: .45rem;
  min-height: 2.6rem;
  padding: .55rem .8rem;
  border: 1px solid var(--primary-color);
  border-radius: 4px;
  background: var(--primary-color);
  color: #fff;
  font-weight: 700;
  cursor: pointer;
  list-style: none;
}
summary::-webkit-details-marker { display: none; }
summary:focus-visible { outline: none; box-shadow: var(--focus-ring); }
.export-panel {
  position: absolute;
  z-index: 15;
  top: calc(100% + .45rem);
  right: 0;
  display: grid;
  width: min(34rem, calc(100vw - 2rem));
  grid-template-columns: minmax(0, 1fr) auto;
  gap: .8rem 1rem;
  padding: 1rem;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--card-background);
  box-shadow: 0 14px 32px rgba(12, 41, 72, .16);
}
p { grid-column: 1 / -1; margin: 0; color: var(--text-color-secondary); font-size: var(--font-supporting); }
label { display: grid; gap: .35rem; color: var(--text-color-primary); font-size: var(--font-ui); font-weight: 650; }
input {
  min-height: 2.5rem;
  padding: .5rem .65rem;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  background: #fff;
  color: var(--text-color-primary);
}
.actions { display: flex; align-items: end; gap: .5rem; }

@media (max-width: 600px) {
  .export-panel { grid-template-columns: 1fr; }
  .actions { align-items: stretch; flex-direction: column; }
  .actions :deep(.p-button) { justify-content: center; width: 100%; }
}
</style>
