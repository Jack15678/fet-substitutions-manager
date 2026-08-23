<template>
  <section class="records-page">
    <header class="page-heading">
      <div>
        <h2>{{ $t('records.title') }}</h2>
        <p>{{ $t('records.description') }}</p>
      </div>
      <span class="today">{{ $t('records.today', { date: records.today || '-' }) }}</span>
    </header>

    <section class="panel">
      <div class="scope-tabs" role="tablist">
        <button v-for="value in scopes" :key="value" :class="{ active: scope === value }" @click="changeScope(value)">
          {{ $t(`records.scopes.${value}`) }}
        </button>
      </div>

      <div v-if="loading" class="empty-state">{{ $t('common.loading') }}</div>
      <div v-else-if="!records.items.length" class="empty-state">{{ $t('records.empty') }}</div>
      <div v-else class="record-list">
        <article v-for="record in records.items" :key="record.id" class="record-card">
          <div class="record-summary">
            <div>
              <strong>{{ formatDate(record.date) }} · {{ record.teacher_name || $t('records.manual') }}</strong>
              <span>{{ joinItems(record.periods.map(period => $t('records.period', { period }))) }}</span>
            </div>
            <div class="record-actions">
              <span :class="['status', record.status]">{{ statusLabel(record.status) }}</span>
              <Button v-if="record.record_type === 'absence' && record.status === 'open'" :label="$t('records.resume')" icon="pi pi-play" size="small" @click="emit('resume-absence', record)" />
              <template v-if="isAdmin && record.record_type === 'absence'">
                <Button :label="$t('common.edit')" icon="pi pi-pencil" size="small" text @click="editAbsence(record)" />
                <Button :label="$t('common.delete')" icon="pi pi-trash" size="small" severity="danger" text @click="removeAbsence(record)" />
              </template>
            </div>
          </div>
          <p class="meta">{{ $t('records.createdBy', { user: record.created_by || '-' }) }}</p>
          <form v-if="editingAbsenceId === record.entity_id" class="record-edit" @submit.prevent="saveAbsence(record)">
            <label>{{ $t('leave.teacher') }}<select v-model.number="absenceEdit.professor_id" required><option v-for="teacher in absenceTeachers" :key="teacher.id" :value="teacher.id">{{ teacher.name }}</option></select></label>
            <label>{{ $t('rescheduling.date') }}<input v-model="absenceEdit.data" type="date" required /></label>
            <div class="edit-periods"><label v-for="period in 9" :key="period"><input v-model="absenceEdit.periods" type="checkbox" :value="period" />{{ $t('records.period', { period }) }}</label></div>
            <div class="edit-actions"><Button type="button" :label="$t('common.cancel')" text @click="resetAbsenceEdit" /><Button type="submit" :label="$t('common.save')" icon="pi pi-save" :disabled="!absenceEdit.periods.length" /></div>
          </form>
          <div v-if="record.adjustments.length" class="adjustments">
            <div v-for="adjustment in record.adjustments" :key="adjustment.id" class="adjustment">
              <div class="adjustment-heading">
                <b>#{{ adjustment.id }} · {{ kindLabel(adjustment.kind) }}</b>
                <div class="record-actions">
                  <span :class="['status', adjustment.status]">{{ statusLabel(adjustment.status) }}</span>
                  <template v-if="isAdmin">
                    <Button :label="$t('records.editReason')" icon="pi pi-pencil" size="small" text @click="editAdjustmentReason(adjustment)" />
                    <Button :label="$t('common.delete')" icon="pi pi-trash" size="small" severity="danger" text @click="removeAdjustment(adjustment)" />
                  </template>
                </div>
              </div>
              <p v-if="adjustment.reason" class="meta">{{ $t('records.reason', { reason: adjustment.reason }) }}</p>
              <div v-for="(leg, index) in adjustment.legs" :key="index" class="leg">
                <span>{{ leg.class_code }} {{ leg.subject }}（{{ joinItems(leg.teacher_names) }}）</span>
                <b>{{ leg.from_date }} {{ $t('records.period', { period: leg.from_period }) }} → {{ leg.to_date }} {{ $t('records.period', { period: leg.to_period }) }}</b>
              </div>
            </div>
          </div>
          <p v-else class="meta">{{ $t('records.noAdjustment') }}</p>
        </article>
      </div>

      <div class="pagination">
        <Button :label="$t('records.previous')" icon="pi pi-chevron-left" text :disabled="records.page <= 1" @click="loadRecords(records.page - 1)" />
        <span>{{ $t('records.page', { page: records.page, pages: records.pages, total: records.total }) }}</span>
        <Button :label="$t('records.next')" icon="pi pi-chevron-right" iconPos="right" text :disabled="records.page >= records.pages" @click="loadRecords(records.page + 1)" />
      </div>
    </section>

  </section>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import axios from 'axios'
import Button from 'primevue/button'

const props = defineProps({ isAdmin: Boolean })
const emit = defineEmits(['resume-absence'])
const { t, locale } = useI18n()
const scopes = ['future', 'today', 'past']
const scope = ref('today')
const records = ref({ today: '', page: 1, pages: 1, total: 0, items: [] })
const loading = ref(false)
const absenceTeachers = ref([])
const editingAbsenceId = ref(null)
const absenceEdit = reactive({ professor_id: null, data: '', periods: [] })

const formatDate = (value) => new Intl.DateTimeFormat(locale.value === 'en' ? 'en-HK' : 'zh-HK', {
  year: 'numeric', month: '2-digit', day: '2-digit', weekday: 'short'
}).format(new Date(`${value}T12:00:00`))
const statusLabel = (value) => t(`records.statuses.${value}`, value)
const kindLabel = (value) => t(`records.kinds.${value}`, value)
const joinItems = (items) => items.join(locale.value === 'en' ? ', ' : '、')

const loadRecords = async (page = 1) => {
  loading.value = true
  try {
    records.value = (await axios.get('/api/records', { params: { scope: scope.value, page, page_size: 20 } })).data
  } finally { loading.value = false }
}
const changeScope = (value) => { scope.value = value; loadRecords(1) }
const resetAbsenceEdit = () => {
  editingAbsenceId.value = null
  Object.assign(absenceEdit, { professor_id: null, data: '', periods: [] })
}
const editAbsence = async (record) => {
  absenceTeachers.value = (await axios.get('/api/rescheduling/teachers', { params: { data: record.date } })).data
  editingAbsenceId.value = record.entity_id
  Object.assign(absenceEdit, { professor_id: record.professor_id, data: record.date, periods: [...record.periods] })
}
const saveAbsence = async (record) => {
  if (record.adjustments.length && !window.confirm(t('records.editRemovesAdjustments'))) return
  await axios.put(`/api/absence-cases/${record.entity_id}`, absenceEdit)
  resetAbsenceEdit(); await loadRecords(records.value.page)
}
const removeAbsence = async (record) => {
  if (!window.confirm(t('records.deleteAbsenceConfirm'))) return
  await axios.delete(`/api/absence-cases/${record.entity_id}/purge`)
  resetAbsenceEdit(); await loadRecords(records.value.page)
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
.page-heading { display: flex; justify-content: space-between; gap: 1.5rem; align-items: flex-start; }
.page-heading h2 { margin: 0 0 .35rem; font-size: clamp(1.65rem, 3vw, 2.15rem); line-height: 1.15; letter-spacing: -.035em; }
.page-heading p, .meta { color: var(--text-color-secondary); }
.today { padding-top: .4rem; color: var(--text-color-secondary); font-size: .8rem; white-space: nowrap; }
.panel { min-width: 0; padding: 1.25rem; border: 1px solid var(--border-color); border-radius: 12px; background: var(--card-background); }
.scope-tabs { display: flex; gap: .2rem; margin: -.25rem 0 1rem; border-bottom: 1px solid var(--border-color); }
.scope-tabs button { padding: .7rem .9rem; border: 0; border-bottom: 2px solid transparent; background: transparent; color: var(--text-color-secondary); font-weight: 650; cursor: pointer; transition: color .15s ease, border-color .15s ease, background-color .15s ease, transform .15s ease; }
.scope-tabs button:hover { background: var(--surface-soft); color: var(--text-color-primary); }
.scope-tabs button.active { border-bottom-color: var(--primary-color); color: var(--primary-color-dark); }
.scope-tabs button:active { transform: translateY(1px); }
.record-list { border: 1px solid var(--border-color); border-radius: 10px; overflow: hidden; }
.record-card { padding: 1rem; border-bottom: 1px solid var(--border-color); }
.record-card:last-child { border-bottom: 0; }
.record-summary, .adjustment-heading { display: flex; align-items: center; justify-content: space-between; gap: 1rem; }
.record-summary > div { display: flex; flex-direction: column; gap: .2rem; }
.record-summary span { color: var(--text-color-secondary); font-size: .82rem; }
.status { display: inline-flex; align-items: center; padding: .24rem .52rem; border-radius: 999px; background: #eef1f4; color: #596476; font-size: .74rem; white-space: nowrap; }
.status.resolved, .status.confirmed { background: #e4f5e9; color: #216a42; }
.status.open { background: #fff4d6; color: #84590e; }
.status.cancelled, .status.reverted { background: #eef1f4; color: #687386; }
.meta { margin: .5rem 0; font-size: .8rem; }
.adjustments { padding-top: .7rem; border-top: 1px solid #edf0f3; }
.adjustment + .adjustment { margin-top: .75rem; }
.leg { display: flex; justify-content: space-between; gap: 1rem; margin-top: .4rem; padding: .55rem .7rem; border-radius: 8px; background: var(--surface-soft); font-size: .8rem; }
.leg b { color: var(--primary-color-dark); text-align: right; }
.pagination { display: flex; align-items: center; justify-content: center; gap: 1rem; margin-top: 1rem; color: var(--text-color-secondary); font-size: .84rem; }
.record-edit > label { display: flex; flex-direction: column; gap: .35rem; color: #344054; font-size: .82rem; font-weight: 650; }
.record-edit select, .record-edit input[type=date] { width: 100%; min-height: 2.55rem; padding: .6rem .7rem; border: 1px solid #cfd6df; border-radius: 8px; background: #fff; color: var(--text-color-primary); }
.record-edit select:hover, .record-edit input:hover { border-color: #aeb8c5; }
.record-edit select:focus, .record-edit input:focus { border-color: var(--primary-color); }
.empty-state { display: grid; place-items: center; min-height: 160px; padding: 1.5rem; border-radius: 10px; background: var(--surface-soft); color: var(--text-color-secondary); text-align: center; }
.record-actions, .edit-actions { display: flex; align-items: center; gap: .35rem; }
.record-edit { display: grid; grid-template-columns: 1fr 180px; gap: .7rem; margin: .65rem 0; padding: .85rem; border-radius: 9px; background: var(--highlight-bg); }
.edit-periods { grid-column: 1 / -1; display: flex; flex-wrap: wrap; gap: .5rem; }
.edit-periods label { display: flex; align-items: center; gap: .25rem; font-size: .8rem; }
.edit-periods input { accent-color: var(--primary-color); }
.edit-actions { grid-column: 1 / -1; justify-content: flex-end; }

@media (max-width: 900px) {
  .leg { flex-direction: column; gap: .2rem; }
  .leg b { text-align: left; }
}

@media (max-width: 600px) {
  .page-heading, .record-summary { flex-direction: column; }
  .today { padding-top: 0; }
  .record-summary, .adjustment-heading { align-items: flex-start; }
  .adjustment-heading { flex-direction: column; }
  .record-actions { justify-content: flex-start; flex-wrap: wrap; }
  .record-edit { grid-template-columns: 1fr; }
  .scope-tabs button { flex: 1; padding: .65rem .4rem; }
  .pagination { justify-content: space-between; gap: .2rem; }
  .panel { padding: 1rem; }
}
</style>
