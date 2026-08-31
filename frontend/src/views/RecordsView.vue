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

      <Transition name="motion-fade" mode="out-in">
      <div v-if="loading" key="loading" class="empty-state">{{ $t('common.loading') }}</div>
      <div v-else-if="!records.items.length" class="empty-state">{{ $t('records.empty') }}</div>
      <div v-else class="records-table-wrap">
        <table class="records-table">
          <thead><tr><th>{{ $t('records.columns.date') }}</th><th>{{ $t('records.columns.teacher') }}</th><th>{{ $t('records.columns.periods') }}</th><th>{{ $t('records.columns.arrangements') }}</th><th>{{ $t('records.columns.status') }}</th><th><span class="sr-only">{{ $t('common.actions') }}</span></th></tr></thead>
          <TransitionGroup name="motion-list" tag="tbody">
            <tr v-for="record in records.items" :key="record.id">
              <td><strong>{{ formatDate(record.date) }}</strong></td>
              <td>{{ record.teacher_name || $t('records.manual') }}</td>
              <td>{{ periodsLabel(record) }}</td>
              <td>{{ arrangementSummary(record) }}</td>
              <td><span :class="['status', record.needs_review ? 'needs-review' : record.status]">{{ record.needs_review ? $t('records.needsReview') : statusLabel(record.status) }}</span></td>
              <td class="row-action"><Button :label="$t('records.view')" text size="small" @click="openDetail(record)" /></td>
            </tr>
          </TransitionGroup>
        </table>
      </div>
      </Transition>

      <div v-if="records.total" class="pagination">
        <Button :label="$t('records.previous')" text :disabled="records.page <= 1" @click="loadRecords(records.page - 1)" />
        <span>{{ $t('records.page', { page: records.page, pages: records.pages, total: records.total }) }}</span>
        <Button :label="$t('records.next')" text :disabled="records.page >= records.pages" @click="loadRecords(records.page + 1)" />
      </div>
    </section>

    <Sidebar v-model:visible="detailVisible" position="right" block-scroll :style="{ width: 'min(100vw, 920px)' }" class="records-sidebar">
      <template #header>
        <div v-if="selectedRecord" class="detail-heading">
          <div>
            <h3>{{ selectedRecord.teacher_name || $t('records.manual') }}</h3>
            <p>{{ formatDate(selectedRecord.date) }}</p>
          </div>
          <span :class="['status', selectedRecord.needs_review ? 'needs-review' : selectedRecord.status]">{{ selectedRecord.needs_review ? $t('records.needsReview') : statusLabel(selectedRecord.status) }}</span>
        </div>
      </template>

      <template v-if="selectedRecord">
        <div class="detail-shell">
          <form v-if="can('records.manage') && editingAbsenceId === selectedRecord.entity_id" class="record-edit" @submit.prevent="saveAbsence(selectedRecord)">
            <h4>{{ $t('records.editAbsence') }}</h4>
            <label>{{ $t('leave.teacher') }}<select v-model.number="absenceEdit.professor_id" required><option v-for="teacher in absenceTeachers" :key="teacher.id" :value="teacher.id">{{ teacher.name }}</option></select></label>
            <label>{{ $t('rescheduling.date') }}<input v-model="absenceEdit.data" type="date" required /></label>
            <label>{{ $t('rescheduling.absenceReason') }}<select v-model="absenceEdit.reason_type" required><option value="">{{ $t('common.selectOption') }}</option><option v-for="reason in absenceReasonTypes" :key="reason" :value="reason">{{ $t(`rescheduling.absenceReasons.${reason}`) }}</option></select></label>
            <label v-if="absenceEdit.reason_type === 'other'">{{ $t('rescheduling.absenceReasons.other') }}<input v-model="absenceEdit.reason_detail" type="text" maxlength="200" :placeholder="$t('rescheduling.otherReasonPlaceholder')" /></label>
            <div class="edit-periods"><label v-for="period in 9" :key="period"><input v-model="absenceEdit.periods" type="checkbox" :value="period" />{{ $t('records.period', { period }) }}</label></div>
            <div class="edit-actions"><Button type="button" :label="$t('common.cancel')" text @click="resetAbsenceEdit" /><Button type="submit" :label="$t('common.save')" :disabled="!absenceEdit.periods.length || !absenceReasonTypes.includes(absenceEdit.reason_type)" /></div>
          </form>

          <div v-else class="detail-workspace">
            <section class="detail-section absence-detail">
              <div class="detail-title"><h4>{{ $t('records.absenceDetails') }}</h4></div>
              <dl class="detail-grid">
                <div><dt>{{ $t('records.columns.date') }}</dt><dd>{{ formatDate(selectedRecord.date) }}</dd></div>
                <div><dt>{{ $t('records.columns.teacher') }}</dt><dd>{{ selectedRecord.teacher_name || $t('records.manual') }}</dd></div>
                <div>
                  <dt>{{ $t('records.columns.periods') }}</dt>
                  <dd class="period-chips">
                    <span v-if="selectedRecord.periods.length === 9" class="period-chip">{{ $t('rescheduling.allDay') }}</span>
                    <template v-else><span v-for="period in selectedRecord.periods" :key="period" class="period-chip">{{ $t('records.period', { period }) }}</span></template>
                  </dd>
                </div>
                <div v-if="selectedRecord.record_type === 'absence'"><dt>{{ $t('rescheduling.absenceReason') }}</dt><dd>{{ absenceReasonLabel(selectedRecord) }}</dd></div>
                <div><dt>{{ $t('records.createdByLabel') }}</dt><dd>{{ selectedRecord.created_by || '—' }}</dd></div>
              </dl>
            </section>

            <section class="detail-section arrangement-detail">
              <div class="detail-title"><h4>{{ $t('records.arrangementDetails') }}</h4><span>{{ arrangementSummary(selectedRecord) }}</span></div>
              <div v-if="!selectedRecord.adjustments.length" class="arrangement-empty">
                <i class="pi pi-file" aria-hidden="true"></i>
                <strong>{{ arrangementSummary(selectedRecord) }}</strong>
                <p class="muted">{{ $t('records.noAdjustment') }}</p>
              </div>
              <TransitionGroup v-else name="motion-list" tag="div" class="adjustment-list">
                <article v-for="adjustment in selectedRecord.adjustments" :key="adjustment.id" class="adjustment">
                  <div class="adjustment-heading">
                    <div><strong>{{ kindLabel(adjustment.kind) }}</strong><small>#{{ adjustment.id }} · {{ executionStateLabel(adjustment.execution_state) }}</small></div>
                    <span :class="['status', adjustment.needs_review ? 'needs-review' : adjustment.status]">{{ adjustment.needs_review ? $t('records.needsReview') : statusLabel(adjustment.status) }}</span>
                  </div>
                  <div v-for="(leg, index) in adjustment.legs" :key="index" class="leg">
                    <span><strong>{{ leg.class_code }} · {{ leg.subject }}</strong><small>{{ joinItems(leg.teacher_names) }}</small></span>
                    <b>{{ leg.from_date }} {{ $t('records.period', { period: leg.from_period }) }} → {{ leg.to_date }} {{ $t('records.period', { period: leg.to_period }) }}</b>
                  </div>
                  <div v-if="can('records.manage')" class="adjustment-actions">
                    <Button v-if="adjustment.can_revert" :label="$t('records.revertAdjustment')" text size="small" severity="danger" @click="removeAdjustment(adjustment)" />
                    <small v-else-if="adjustment.status === 'confirmed'">{{ $t('records.cannotRevertStarted') }}</small>
                  </div>
                </article>
              </TransitionGroup>
            </section>
          </div>

          <div v-if="selectedRecord.record_type === 'absence' && editingAbsenceId !== selectedRecord.entity_id && (can('records.manage') || (can('absence.create') && selectedRecord.status === 'open'))" class="admin-actions">
            <Button v-if="can('absence.create') && selectedRecord.status === 'open'" :label="$t('records.resume')" @click="resumeSelected" />
            <Button v-if="can('records.manage')" :label="$t('records.editAbsence')" outlined @click="editAbsence(selectedRecord)" />
            <Button v-if="can('records.manage')" :label="$t('common.delete')" severity="danger" text @click="removeAbsence(selectedRecord)" />
          </div>
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

defineProps({ can: { type: Function, required: true } })
const emit = defineEmits(['resume-absence'])
const { t, locale } = useI18n()
const filters = reactive({ q: '', date_from: '', date_to: '', status: '', kind: '' })
const records = ref({ page: 1, pages: 1, total: 0, items: [] })
const loading = ref(false)
const detailVisible = ref(false)
const selectedRecord = ref(null)
const absenceTeachers = ref([])
const editingAbsenceId = ref(null)
const absenceReasonTypes = ['sick', 'follow_up', 'team_training', 'other']
const absenceEdit = reactive({ professor_id: null, data: '', periods: [], reason_type: '', reason_detail: '' })

const formatDate = (value) => new Intl.DateTimeFormat(locale.value === 'en' ? 'en-HK' : 'zh-HK', {
  year: 'numeric', month: '2-digit', day: '2-digit', weekday: 'short'
}).format(new Date(`${value}T12:00:00`))
const statusLabel = (value) => t(`records.statuses.${value}`, value)
const kindLabel = (value) => t(`records.kinds.${value}`, value)
const executionStateLabel = (value) => t(`records.executionStates.${value}`, value)
const joinItems = (items) => items.join(locale.value === 'en' ? ', ' : '、')
const periodsLabel = (record) => record.periods.length === 9
  ? t('rescheduling.allDay')
  : joinItems(record.periods.map(period => t('records.period', { period })))
const arrangementSummary = (record) => record.adjustments.length
  ? t('records.arrangementCount', { count: record.adjustments.length })
  : t('records.noAdjustmentShort')
const absenceReasonLabel = (record) => {
  if (!record.reason_type) return t('rescheduling.absenceReasonMissing')
  const label = t(`rescheduling.absenceReasons.${record.reason_type}`)
  return record.reason_type === 'other' && record.reason_detail?.trim() ? `${label}：${record.reason_detail.trim()}` : label
}

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
  Object.assign(absenceEdit, { professor_id: null, data: '', periods: [], reason_type: '', reason_detail: '' })
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
  Object.assign(absenceEdit, {
    professor_id: record.professor_id,
    data: record.date,
    periods: [...record.periods],
    reason_type: record.reason_type || '',
    reason_detail: record.reason_detail || '',
  })
}
const saveAbsence = async (record) => {
  const identityChanged = Number(record.professor_id) !== Number(absenceEdit.professor_id)
    || record.date !== absenceEdit.data
  if (identityChanged && record.adjustments.length) {
    window.alert(t('records.confirmedIdentityLocked'))
    return
  }
  await axios.put(`/api/absence-cases/${record.entity_id}`, {
    professor_id: absenceEdit.professor_id,
    data: absenceEdit.data,
    periods: absenceEdit.periods.map(Number),
    reason_type: absenceEdit.reason_type,
    reason_detail: absenceEdit.reason_type === 'other' ? absenceEdit.reason_detail.trim() || null : null,
  })
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
const removeAdjustment = async (adjustment) => {
  if (!window.confirm(t('records.revertAdjustmentConfirm'))) return
  await axios.post(`/api/adjustments/${adjustment.id}/revert`)
  await loadRecords(records.value.page)
}

onMounted(loadRecords)
</script>

<style scoped>
.records-page { display: grid; gap: 1.25rem; color: var(--text-color-primary); }
.page-heading h2 { margin: 0 0 .35rem; font-size: clamp(1.65rem, 3vw, 2.15rem); line-height: 1.15; letter-spacing: -.035em; }
.page-heading p, .muted, .result-bar span, .detail-heading p, .detail-title span { color: var(--text-color-secondary); }
.panel { min-width: 0; padding: 1.25rem; border: 1px solid var(--border-color); border-radius: var(--radius-lg); background: var(--card-background); box-shadow: var(--shadow-panel); }
.record-filters { display: grid; grid-template-columns: minmax(210px, 1.4fr) repeat(4, minmax(130px, .75fr)) auto; align-items: end; gap: .75rem; }
.record-filters label { display: flex; min-width: 0; flex-direction: column; gap: .35rem; color: #344054; font-size: var(--font-ui); font-weight: 650; }
.record-filters input, .record-filters select, .record-edit select, .record-edit input[type=date], .record-edit input[type=text] { width: 100%; min-height: 2.5rem; padding: .55rem .65rem; border: 1px solid #cfd6df; border-radius: 6px; background: #fff; color: var(--text-color-primary); }
.filter-actions { display: flex; align-items: center; gap: .25rem; }
.result-bar { display: flex; align-items: baseline; justify-content: space-between; gap: 1rem; margin: 1.2rem 0 .6rem; font-size: var(--font-ui); }
.records-table-wrap { overflow-x: auto; border: 1px solid var(--border-color); border-radius: 8px; }
.records-table { width: 100%; min-width: 900px; border-collapse: collapse; }
.records-table th, .records-table td { padding: .75rem; border-bottom: 1px solid #edf0f3; text-align: left; font-size: var(--font-data); }
.records-table th { background: var(--surface-soft); color: #526071; font-weight: 700; }
.records-table tbody tr:last-child td { border-bottom: 0; }
.records-table tbody tr:hover { background: #fbfcfe; }
.row-action { width: 1%; text-align: right !important; white-space: nowrap; }
.status { display: inline-flex; align-items: center; padding: .24rem .52rem; border-radius: 999px; background: #eef1f4; color: #596476; font-size: var(--font-supporting); white-space: nowrap; }
.status.resolved, .status.confirmed { background: #e4f5e9; color: #216a42; }
.status.open { background: #fff4d6; color: #84590e; }
.status.needs-review { background: #fff0d5; color: #8a4f08; }
.empty-state { display: grid; min-height: 140px; place-items: center; border: 1px dashed var(--border-strong); border-radius: var(--radius-md); background: rgba(245, 247, 248, .72); color: var(--text-color-secondary); }
.pagination { display: flex; align-items: center; justify-content: center; gap: 1rem; margin-top: 1rem; color: var(--text-color-secondary); font-size: var(--font-ui); }
:global(.records-sidebar .p-sidebar-header) { padding: 1.25rem 1.5rem; border-bottom: 1px solid var(--border-color); }
:global(.records-sidebar .p-sidebar-content) { display: flex; flex-direction: column; padding: 0; background: #f7f9fb; }
.detail-heading { display: flex; min-width: 0; flex: 1; align-items: center; justify-content: space-between; gap: 1rem; padding-right: .75rem; }
.detail-heading h3, .detail-heading p, .detail-section h4, .record-edit h4 { margin: 0; }
.detail-heading h3 { color: var(--primary-color-dark); font-size: 1.35rem; letter-spacing: -.02em; }
.detail-heading p { margin-top: .25rem; font-size: var(--font-data); font-variant-numeric: tabular-nums; }
.detail-shell { display: flex; min-height: calc(100dvh - 5rem); flex-direction: column; }
.detail-workspace { display: grid; grid-template-columns: minmax(0, .95fr) minmax(0, 1.05fr); flex: 1; gap: 1rem; align-items: stretch; padding: 1.5rem; }
.detail-section { display: flex; min-width: 0; min-height: clamp(28rem, 62dvh, 40rem); flex-direction: column; padding: 1.35rem; border: 1px solid var(--border-color); border-radius: 10px; background: #fff; }
.detail-title, .adjustment-heading, .admin-actions, .edit-actions { display: flex; align-items: center; justify-content: space-between; gap: .75rem; }
.detail-title { min-height: 2.35rem; padding-bottom: 1rem; border-bottom: 1px solid #e4e9ef; }
.detail-title h4 { color: var(--primary-color-dark); font-size: var(--font-data); letter-spacing: -.01em; }
.detail-title span { font-size: var(--font-supporting); }
.detail-grid { display: grid; margin: 0; }
.detail-grid div { display: grid; grid-template-columns: minmax(6.75rem, .7fr) minmax(0, 1.3fr); min-width: 0; align-items: center; gap: .75rem; padding: 1rem 0; border-bottom: 1px solid #e9edf2; }
.detail-grid div:last-child { border-bottom: 0; }
.detail-grid dt { color: var(--text-color-secondary); font-size: var(--font-supporting); }
.detail-grid dd { min-width: 0; margin: 0; font-size: var(--font-data); font-weight: 650; overflow-wrap: anywhere; }
.period-chips { display: flex; flex-wrap: wrap; gap: .35rem; }
.period-chip { padding: .3rem .52rem; border-radius: 5px; background: #edf3fb; color: var(--primary-color-dark); font-size: var(--font-ui); white-space: nowrap; }
.arrangement-detail { border-color: #cbdcf0; background: #f3f7fc; }
.arrangement-empty { display: flex; min-height: 22rem; flex: 1; align-items: center; justify-content: center; flex-direction: column; padding: 2rem 1rem; text-align: center; }
.arrangement-empty > i { display: grid; width: 3.5rem; height: 3.5rem; margin-bottom: 1rem; place-items: center; border: 1px solid #b8cce4; border-radius: 50%; color: #6f91b7; font-size: 1.4rem; }
.arrangement-empty > strong { color: var(--primary-color-dark); font-size: 1.1rem; }
.arrangement-empty p { max-width: 28ch; margin: .45rem 0 1.25rem; line-height: 1.55; }
.adjustment-list { overflow: auto; }
.adjustment { padding: 1rem 0; }
.adjustment + .adjustment { border-top: 1px solid #dce6f1; }
.adjustment-heading > div { display: flex; flex-direction: column; gap: .1rem; }
.adjustment-heading small, .leg small { color: var(--text-color-secondary); }
.leg { display: grid; grid-template-columns: minmax(7rem, .7fr) minmax(0, 1.3fr); gap: .75rem; margin-top: .5rem; padding: .65rem; border: 1px solid #e0e8f1; border-radius: 6px; background: #fff; font-size: var(--font-data); }
.leg span { display: flex; min-width: 0; flex-direction: column; gap: .15rem; }
.leg b { color: var(--primary-color-dark); text-align: right; overflow-wrap: anywhere; }
.adjustment-actions { display: flex; justify-content: flex-end; gap: .25rem; margin-top: .35rem; }
.admin-actions { position: sticky; bottom: 0; z-index: 1; min-height: 4.75rem; justify-content: flex-end; padding: 1rem 1.5rem; border-top: 1px solid var(--border-color); background: rgba(255, 255, 255, .96); }
.record-edit { display: grid; grid-template-columns: 1fr 180px; gap: .7rem; margin: 1.5rem; padding: 1.25rem; border: 1px solid var(--border-color); border-radius: 10px; background: #fff; }
.record-edit h4, .edit-periods, .edit-actions { grid-column: 1 / -1; }
.record-edit > label { display: flex; flex-direction: column; gap: .35rem; font-size: var(--font-ui); font-weight: 650; }
.edit-periods { display: flex; flex-wrap: wrap; gap: .5rem; }
.edit-periods label { display: flex; align-items: center; gap: .25rem; font-size: var(--font-ui); }
.edit-periods input { accent-color: var(--primary-color); }
.edit-actions { justify-content: flex-end; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }

@media (max-width: 1100px) { .record-filters { grid-template-columns: repeat(3, minmax(0, 1fr)); } .filter-actions { justify-content: flex-end; } }
@media (max-width: 720px) { .panel { padding: 1rem; } .record-filters { grid-template-columns: 1fr; } .filter-actions { justify-content: flex-end; } .result-bar { align-items: flex-start; flex-direction: column; } :global(.records-sidebar .p-sidebar-header) { padding: 1rem; } .detail-workspace { grid-template-columns: 1fr; padding: 1rem; } .detail-section { min-height: auto; } .arrangement-empty { min-height: 16rem; } .admin-actions { padding: .85rem 1rem; } .record-edit { grid-template-columns: 1fr; margin: 1rem; } .leg { grid-template-columns: 1fr; } .leg b { text-align: left; } .pagination { justify-content: space-between; gap: .25rem; } }
</style>
