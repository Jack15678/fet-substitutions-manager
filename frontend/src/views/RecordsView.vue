<template>
  <section class="records-page">
    <header class="page-heading">
      <h2>{{ $t('records.title') }}</h2>
      <p>{{ $t('records.description') }}</p>
    </header>

    <section class="panel">
      <form class="record-filters" @submit.prevent="loadRecords(1)">
        <label class="search-field">
          <span>{{ $t('records.search') }}</span>
          <input v-model.trim="filters.q" type="search" :placeholder="$t('records.searchPlaceholder')" />
        </label>
        <label><span>{{ $t('records.dateFrom') }}</span><input v-model="filters.date_from" type="date" :max="filters.date_to || undefined" /></label>
        <label><span>{{ $t('records.dateTo') }}</span><input v-model="filters.date_to" type="date" :min="filters.date_from || undefined" /></label>
        <label><span>{{ $t('records.status') }}</span><select v-model="filters.status"><option value="">{{ $t('common.all') }}</option><option value="open">{{ $t('records.filterStatuses.open') }}</option><option value="completed">{{ $t('records.filterStatuses.completed') }}</option></select></label>
        <label><span>{{ $t('records.type') }}</span><select v-model="filters.kind"><option value="">{{ $t('common.all') }}</option><option value="swap">{{ $t('records.filterKinds.swap') }}</option><option value="cover">{{ $t('records.filterKinds.cover') }}</option><option value="manual">{{ $t('records.filterKinds.manual') }}</option></select></label>
        <div class="filter-actions"><Button type="button" :label="$t('records.reset')" text @click="resetFilters" /><Button type="submit" :label="$t('records.apply')" /></div>
      </form>

      <div class="result-bar">
        <strong>{{ $t('records.resultCount', { count: records.total }) }}</strong>
        <span>{{ $t('records.resultHint') }}</span>
      </div>

      <div v-if="loading" class="empty-state">{{ $t('common.loading') }}</div>
      <div v-else-if="!records.items.length" class="empty-state">{{ $t('records.empty') }}</div>
      <div v-else class="records-table-wrap">
        <table class="records-table">
          <thead><tr><th>{{ $t('records.columns.date') }}</th><th>{{ $t('records.columns.teacher') }}</th><th>{{ $t('records.columns.periods') }}</th><th>{{ $t('records.columns.arrangements') }}</th><th>{{ $t('records.columns.status') }}</th><th><span class="sr-only">{{ $t('common.actions') }}</span></th></tr></thead>
          <tbody>
            <tr v-for="record in records.items" :key="record.id">
              <td><strong>{{ formatDate(record.date) }}</strong></td>
              <td>{{ record.teacher_name || $t('records.manual') }}</td>
              <td>{{ periodsLabel(record) }}</td>
              <td>{{ arrangementSummary(record) }}</td>
              <td><span :class="['status', record.status]">{{ statusLabel(record.status) }}</span></td>
              <td class="row-action"><Button :label="$t('records.view')" text size="small" @click="openDetail(record)" /></td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="records.total" class="pagination">
        <Button :label="$t('records.previous')" text :disabled="records.page <= 1" @click="loadRecords(records.page - 1)" />
        <span>{{ $t('records.page', { page: records.page, pages: records.pages, total: records.total }) }}</span>
        <Button :label="$t('records.next')" text :disabled="records.page >= records.pages" @click="loadRecords(records.page + 1)" />
      </div>
    </section>

    <Sidebar v-model:visible="detailVisible" position="right" :style="{ width: 'min(100vw, 680px)' }" class="records-sidebar">
      <template #header>
        <div v-if="selectedRecord" class="detail-heading">
          <h3>{{ selectedRecord.teacher_name || $t('records.manual') }}</h3>
          <p>{{ formatDate(selectedRecord.date) }}</p>
        </div>
      </template>

      <template v-if="selectedRecord">
        <section class="detail-section">
          <div class="detail-title"><h4>{{ $t('records.absenceDetails') }}</h4><span :class="['status', selectedRecord.status]">{{ statusLabel(selectedRecord.status) }}</span></div>
          <dl class="detail-grid">
            <div><dt>{{ $t('records.columns.date') }}</dt><dd>{{ formatDate(selectedRecord.date) }}</dd></div>
            <div><dt>{{ $t('records.columns.teacher') }}</dt><dd>{{ selectedRecord.teacher_name || $t('records.manual') }}</dd></div>
            <div><dt>{{ $t('records.columns.periods') }}</dt><dd>{{ periodsLabel(selectedRecord) }}</dd></div>
            <div><dt>{{ $t('records.createdByLabel') }}</dt><dd>{{ selectedRecord.created_by || '—' }}</dd></div>
          </dl>
          <Button v-if="selectedRecord.record_type === 'absence' && selectedRecord.status === 'open'" :label="$t('records.resume')" @click="resumeSelected" />
        </section>

        <form v-if="editingAbsenceId === selectedRecord.entity_id" class="record-edit" @submit.prevent="saveAbsence(selectedRecord)">
          <h4>{{ $t('records.editAbsence') }}</h4>
          <label>{{ $t('leave.teacher') }}<select v-model.number="absenceEdit.professor_id" required><option v-for="teacher in absenceTeachers" :key="teacher.id" :value="teacher.id">{{ teacher.name }}</option></select></label>
          <label>{{ $t('rescheduling.date') }}<input v-model="absenceEdit.data" type="date" required /></label>
          <div class="edit-periods"><label v-for="period in 9" :key="period"><input v-model="absenceEdit.periods" type="checkbox" :value="period" />{{ $t('records.period', { period }) }}</label></div>
          <div class="edit-actions"><Button type="button" :label="$t('common.cancel')" text @click="resetAbsenceEdit" /><Button type="submit" :label="$t('common.save')" :disabled="!absenceEdit.periods.length" /></div>
        </form>

        <section class="detail-section">
          <div class="detail-title"><h4>{{ $t('records.arrangementDetails') }}</h4><span>{{ arrangementSummary(selectedRecord) }}</span></div>
          <p v-if="!selectedRecord.adjustments.length" class="muted">{{ $t('records.noAdjustment') }}</p>
          <article v-for="adjustment in selectedRecord.adjustments" v-else :key="adjustment.id" class="adjustment">
            <div class="adjustment-heading">
              <div><strong>{{ kindLabel(adjustment.kind) }}</strong><small>#{{ adjustment.id }}</small></div>
              <span :class="['status', adjustment.status]">{{ statusLabel(adjustment.status) }}</span>
            </div>
            <p v-if="adjustment.reason" class="muted">{{ $t('records.reason', { reason: adjustment.reason }) }}</p>
            <div v-for="(leg, index) in adjustment.legs" :key="index" class="leg">
              <span><strong>{{ leg.class_code }} · {{ leg.subject }}</strong><small>{{ joinItems(leg.teacher_names) }}</small></span>
              <b>{{ leg.from_date }} {{ $t('records.period', { period: leg.from_period }) }} → {{ leg.to_date }} {{ $t('records.period', { period: leg.to_period }) }}</b>
            </div>
            <div v-if="isAdmin" class="adjustment-actions"><Button :label="$t('records.editReason')" text size="small" @click="editAdjustmentReason(adjustment)" /><Button :label="$t('common.delete')" text size="small" severity="danger" @click="removeAdjustment(adjustment)" /></div>
          </article>
        </section>

        <div v-if="isAdmin && selectedRecord.record_type === 'absence' && editingAbsenceId !== selectedRecord.entity_id" class="admin-actions">
          <Button :label="$t('common.edit')" outlined @click="editAbsence(selectedRecord)" />
          <Button :label="$t('common.delete')" severity="danger" text @click="removeAbsence(selectedRecord)" />
        </div>
      </template>
    </Sidebar>
  </section>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import axios from 'axios'
import Button from 'primevue/button'
import Sidebar from 'primevue/sidebar'

const props = defineProps({ isAdmin: Boolean })
const emit = defineEmits(['resume-absence'])
const { t, locale } = useI18n()
const filters = reactive({ q: '', date_from: '', date_to: '', status: '', kind: '' })
const records = ref({ page: 1, pages: 1, total: 0, items: [] })
const loading = ref(false)
const detailVisible = ref(false)
const selectedRecord = ref(null)
const absenceTeachers = ref([])
const editingAbsenceId = ref(null)
const absenceEdit = reactive({ professor_id: null, data: '', periods: [] })

const formatDate = (value) => new Intl.DateTimeFormat(locale.value === 'en' ? 'en-HK' : 'zh-HK', {
  year: 'numeric', month: '2-digit', day: '2-digit', weekday: 'short'
}).format(new Date(`${value}T12:00:00`))
const statusLabel = (value) => t(`records.statuses.${value}`, value)
const kindLabel = (value) => t(`records.kinds.${value}`, value)
const joinItems = (items) => items.join(locale.value === 'en' ? ', ' : '、')
const periodsLabel = (record) => record.periods.length === 9
  ? t('rescheduling.allDay')
  : joinItems(record.periods.map(period => t('records.period', { period })))
const arrangementSummary = (record) => record.adjustments.length
  ? t('records.arrangementCount', { count: record.adjustments.length })
  : t('records.noAdjustmentShort')

const loadRecords = async (page = 1) => {
  loading.value = true
  try {
    const params = { scope: 'all', page, page_size: 20, ...Object.fromEntries(Object.entries(filters).filter(([, value]) => value)) }
    records.value = (await axios.get('/api/records', { params })).data
    if (selectedRecord.value) {
      selectedRecord.value = records.value.items.find(item => item.id === selectedRecord.value.id) || null
      if (!selectedRecord.value) detailVisible.value = false
    }
  } finally { loading.value = false }
}
const resetFilters = () => {
  Object.assign(filters, { q: '', date_from: '', date_to: '', status: '', kind: '' })
  loadRecords(1)
}
const resetAbsenceEdit = () => {
  editingAbsenceId.value = null
  Object.assign(absenceEdit, { professor_id: null, data: '', periods: [] })
}
const openDetail = (record) => {
  resetAbsenceEdit()
  selectedRecord.value = record
  detailVisible.value = true
}
const resumeSelected = () => {
  detailVisible.value = false
  emit('resume-absence', selectedRecord.value)
}
const editAbsence = async (record) => {
  absenceTeachers.value = (await axios.get('/api/rescheduling/teachers', { params: { data: record.date } })).data
  editingAbsenceId.value = record.entity_id
  Object.assign(absenceEdit, { professor_id: record.professor_id, data: record.date, periods: [...record.periods] })
}
const saveAbsence = async (record) => {
  if (record.adjustments.length && !window.confirm(t('records.editRemovesAdjustments'))) return
  await axios.put(`/api/absence-cases/${record.entity_id}`, absenceEdit)
  resetAbsenceEdit()
  await loadRecords(records.value.page)
}
const removeAbsence = async (record) => {
  if (!window.confirm(t('records.deleteAbsenceConfirm'))) return
  await axios.delete(`/api/absence-cases/${record.entity_id}/purge`)
  detailVisible.value = false
  selectedRecord.value = null
  resetAbsenceEdit()
  await loadRecords(records.value.page)
}
const editAdjustmentReason = async (adjustment) => {
  const reason = window.prompt(t('records.reasonPrompt'), adjustment.reason || '')
  if (reason === null) return
  await axios.put(`/api/adjustments/${adjustment.id}`, { reason })
  await loadRecords(records.value.page)
}
const removeAdjustment = async (adjustment) => {
  if (!window.confirm(t('records.deleteAdjustmentConfirm'))) return
  await axios.delete(`/api/adjustments/${adjustment.id}`)
  await loadRecords(records.value.page)
}

onMounted(loadRecords)
</script>

<style scoped>
.records-page { display: grid; gap: 1.25rem; color: var(--text-color-primary); }
.page-heading h2 { margin: 0 0 .35rem; font-size: clamp(1.65rem, 3vw, 2.15rem); line-height: 1.15; letter-spacing: -.035em; }
.page-heading p, .muted, .result-bar span, .detail-heading p, .detail-title span { color: var(--text-color-secondary); }
.panel { min-width: 0; padding: 1.25rem; border: 1px solid var(--border-color); border-radius: 12px; background: var(--card-background); }
.record-filters { display: grid; grid-template-columns: minmax(210px, 1.4fr) repeat(4, minmax(130px, .75fr)) auto; align-items: end; gap: .75rem; }
.record-filters label { display: flex; min-width: 0; flex-direction: column; gap: .35rem; color: #344054; font-size: .78rem; font-weight: 650; }
.record-filters input, .record-filters select, .record-edit select, .record-edit input[type=date] { width: 100%; min-height: 2.5rem; padding: .55rem .65rem; border: 1px solid #cfd6df; border-radius: 6px; background: #fff; color: var(--text-color-primary); }
.filter-actions { display: flex; align-items: center; gap: .25rem; }
.result-bar { display: flex; align-items: baseline; justify-content: space-between; gap: 1rem; margin: 1.2rem 0 .6rem; font-size: .82rem; }
.records-table-wrap { overflow-x: auto; border: 1px solid var(--border-color); border-radius: 8px; }
.records-table { width: 100%; min-width: 850px; border-collapse: collapse; }
.records-table th, .records-table td { padding: .75rem; border-bottom: 1px solid #edf0f3; text-align: left; font-size: .82rem; }
.records-table th { background: var(--surface-soft); color: #526071; font-weight: 700; }
.records-table tbody tr:last-child td { border-bottom: 0; }
.records-table tbody tr:hover { background: #fbfcfe; }
.row-action { width: 1%; text-align: right !important; white-space: nowrap; }
.status { display: inline-flex; align-items: center; padding: .24rem .52rem; border-radius: 999px; background: #eef1f4; color: #596476; font-size: .74rem; white-space: nowrap; }
.status.resolved, .status.confirmed { background: #e4f5e9; color: #216a42; }
.status.open { background: #fff4d6; color: #84590e; }
.empty-state { display: grid; min-height: 170px; place-items: center; border-radius: 8px; background: var(--surface-soft); color: var(--text-color-secondary); }
.pagination { display: flex; align-items: center; justify-content: center; gap: 1rem; margin-top: 1rem; color: var(--text-color-secondary); font-size: .82rem; }
.detail-heading h3, .detail-heading p, .detail-section h4, .record-edit h4 { margin: 0; }
.detail-heading p { margin-top: .2rem; font-size: .8rem; }
.detail-section, .record-edit { margin-bottom: 1rem; padding: 1rem; border: 1px solid var(--border-color); border-radius: 8px; background: #fff; }
.detail-title, .adjustment-heading, .admin-actions, .edit-actions { display: flex; align-items: center; justify-content: space-between; gap: .75rem; }
.detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: .85rem; margin: 1rem 0; }
.detail-grid div { min-width: 0; }
.detail-grid dt { color: var(--text-color-secondary); font-size: .72rem; }
.detail-grid dd { margin: .2rem 0 0; font-size: .86rem; font-weight: 650; }
.adjustment { margin-top: .8rem; padding-top: .8rem; border-top: 1px solid #edf0f3; }
.adjustment-heading > div { display: flex; flex-direction: column; gap: .1rem; }
.adjustment-heading small, .leg small { color: var(--text-color-secondary); }
.leg { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 1rem; margin-top: .5rem; padding: .65rem; border-radius: 6px; background: var(--surface-soft); font-size: .78rem; }
.leg span { display: flex; min-width: 0; flex-direction: column; gap: .15rem; }
.leg b { color: var(--primary-color-dark); text-align: right; }
.adjustment-actions { display: flex; justify-content: flex-end; gap: .25rem; margin-top: .35rem; }
.admin-actions { justify-content: flex-end; padding-top: .25rem; }
.record-edit { display: grid; grid-template-columns: 1fr 180px; gap: .7rem; background: var(--highlight-bg); }
.record-edit h4, .edit-periods, .edit-actions { grid-column: 1 / -1; }
.record-edit > label { display: flex; flex-direction: column; gap: .35rem; font-size: .78rem; font-weight: 650; }
.edit-periods { display: flex; flex-wrap: wrap; gap: .5rem; }
.edit-periods label { display: flex; align-items: center; gap: .25rem; font-size: .78rem; }
.edit-periods input { accent-color: var(--primary-color); }
.edit-actions { justify-content: flex-end; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }

@media (max-width: 1100px) { .record-filters { grid-template-columns: repeat(3, minmax(0, 1fr)); } .filter-actions { justify-content: flex-end; } }
@media (max-width: 720px) { .panel { padding: 1rem; } .record-filters { grid-template-columns: 1fr; } .filter-actions { justify-content: flex-end; } .result-bar { align-items: flex-start; flex-direction: column; } .detail-grid, .record-edit { grid-template-columns: 1fr; } .leg { grid-template-columns: 1fr; } .leg b { text-align: left; } .pagination { justify-content: space-between; gap: .25rem; } }
</style>
