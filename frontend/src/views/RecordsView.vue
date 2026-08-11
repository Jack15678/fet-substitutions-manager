<template>
  <section class="records-page">
    <header class="page-heading">
      <div>
        <p class="eyebrow">{{ $t('records.eyebrow') }}</p>
        <h2>{{ $t('records.title') }}</h2>
        <p>{{ $t('records.description') }}</p>
      </div>
      <span class="today">{{ $t('records.today', { date: records.today || '—' }) }}</span>
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
              <template v-if="isAdmin && record.record_type === 'absence'">
                <Button :label="$t('common.edit')" icon="pi pi-pencil" size="small" text @click="editAbsence(record)" />
                <Button :label="$t('common.delete')" icon="pi pi-trash" size="small" severity="danger" text @click="removeAbsence(record)" />
              </template>
            </div>
          </div>
          <p class="meta">{{ $t('records.createdBy', { user: record.created_by || '—' }) }}</p>
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

    <section v-if="isAdmin" class="panel leave-panel">
      <div class="leave-heading">
        <div><h3>{{ $t('leave.title') }}</h3><p>{{ $t('leave.description') }}</p></div>
        <Button v-if="editingId" :label="$t('leave.cancelEdit')" text @click="resetLeave" />
      </div>
      <form class="leave-form" @submit.prevent="saveLeave">
        <label>{{ $t('leave.teacher') }}
          <select v-model.number="leave.professor_id" required>
            <option :value="null">{{ $t('common.selectOption') }}</option>
            <option v-for="teacher in teachers" :key="teacher.id" :value="teacher.id">{{ teacher.name }}</option>
          </select>
        </label>
        <label>{{ $t('leave.type') }}
          <select v-model="leave.leave_type" required>
            <option value="sick">{{ $t('leave.types.sick') }}</option>
            <option value="maternity">{{ $t('leave.types.maternity') }}</option>
            <option value="other">{{ $t('leave.types.other') }}</option>
          </select>
        </label>
        <label>{{ $t('leave.startDate') }}<input v-model="leave.start_date" type="date" required /></label>
        <label>{{ $t('leave.endDate') }}<input v-model="leave.end_date" type="date" required /></label>
        <Button type="submit" :label="editingId ? $t('leave.update') : $t('leave.add')" icon="pi pi-save" :loading="leaveBusy" />
      </form>
      <div v-if="leaves.length" class="leave-list">
        <article v-for="item in leaves" :key="item.id">
          <div><strong>{{ item.teacher_name }}</strong><span>{{ leaveTypeLabel(item.leave_type) }} · {{ item.start_date }} → {{ item.end_date }}</span></div>
          <div><Button :label="$t('common.edit')" icon="pi pi-pencil" text @click="editLeave(item)" /><Button :label="$t('common.delete')" icon="pi pi-trash" severity="danger" text @click="removeLeave(item.id)" /></div>
        </article>
      </div>
      <p v-else class="empty-state compact">{{ $t('leave.empty') }}</p>
    </section>
  </section>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import axios from 'axios'
import Button from 'primevue/button'

const props = defineProps({ isAdmin: Boolean })
const { t, locale } = useI18n()
const scopes = ['future', 'today', 'past']
const scope = ref('today')
const records = ref({ today: '', page: 1, pages: 1, total: 0, items: [] })
const loading = ref(false)
const leaves = ref([])
const teachers = ref([])
const absenceTeachers = ref([])
const leaveBusy = ref(false)
const editingId = ref(null)
const leave = reactive({ professor_id: null, leave_type: 'sick', start_date: '', end_date: '' })
const editingAbsenceId = ref(null)
const absenceEdit = reactive({ professor_id: null, data: '', periods: [] })

const formatDate = (value) => new Intl.DateTimeFormat(locale.value === 'en' ? 'en-HK' : 'zh-HK', {
  year: 'numeric', month: '2-digit', day: '2-digit', weekday: 'short'
}).format(new Date(`${value}T12:00:00`))
const statusLabel = (value) => t(`records.statuses.${value}`, value)
const kindLabel = (value) => t(`records.kinds.${value}`, value)
const leaveTypeLabel = (value) => t(`leave.types.${value}`, value)
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
const loadLeaves = async () => {
  const [leaveResponse, teacherResponse] = await Promise.all([
    axios.get('/api/teacher-leaves'), axios.get('/api/rescheduling/teachers')
  ])
  leaves.value = leaveResponse.data
  teachers.value = teacherResponse.data
}
const resetLeave = () => {
  editingId.value = null
  Object.assign(leave, { professor_id: null, leave_type: 'sick', start_date: '', end_date: '' })
}
const editLeave = (item) => {
  editingId.value = item.id
  Object.assign(leave, { professor_id: item.professor_id, leave_type: item.leave_type, start_date: item.start_date, end_date: item.end_date })
}
const saveLeave = async () => {
  leaveBusy.value = true
  try {
    const url = editingId.value ? `/api/teacher-leaves/${editingId.value}` : '/api/teacher-leaves'
    await axios[editingId.value ? 'put' : 'post'](url, leave)
    resetLeave(); await loadLeaves()
  } finally { leaveBusy.value = false }
}
const removeLeave = async (id) => {
  await axios.delete(`/api/teacher-leaves/${id}`)
  if (editingId.value === id) resetLeave()
  await loadLeaves()
}

onMounted(async () => {
  await loadRecords()
  if (props.isAdmin) await loadLeaves()
})
</script>

<style scoped>
.records-page{display:flex;flex-direction:column;gap:1.25rem;color:#172033}.page-heading,.leave-heading{display:flex;justify-content:space-between;gap:1.5rem;align-items:flex-start}.page-heading h2{font-size:2rem;margin:.15rem 0}.page-heading p,.leave-heading p,.meta{color:#657084}.eyebrow{color:#4965d6!important;font-weight:700;text-transform:uppercase;font-size:.78rem;letter-spacing:.08em}.today{background:#eef2ff;color:#4256b5;padding:.5rem .75rem;border-radius:999px;font-size:.82rem;white-space:nowrap}.panel{background:#fff;border:1px solid #e4e8f0;border-radius:14px;padding:1.2rem;box-shadow:0 4px 18px rgba(35,45,75,.05)}.scope-tabs{display:flex;gap:.4rem;border-bottom:1px solid #e7eaf0;margin:-.2rem 0 1rem}.scope-tabs button{border:0;background:transparent;padding:.75rem 1rem;color:#657084;font-weight:650;cursor:pointer;border-bottom:3px solid transparent}.scope-tabs button.active{color:#3f55bc;border-bottom-color:#4965d6}.record-list{display:flex;flex-direction:column;gap:.8rem}.record-card{border:1px solid #e1e5ed;border-radius:11px;padding:1rem}.record-summary,.adjustment-heading,.leave-list article{display:flex;align-items:center;justify-content:space-between;gap:1rem}.record-summary>div,.leave-list article>div:first-child{display:flex;flex-direction:column;gap:.2rem}.record-summary span,.leave-list span{font-size:.82rem;color:#657084}.status{font-size:.74rem;padding:.28rem .55rem;border-radius:999px;background:#edf0f5;color:#5c6575;white-space:nowrap}.status.resolved,.status.confirmed{background:#e7f7ee;color:#237448}.status.open{background:#fff3d9;color:#8a5b16}.status.cancelled,.status.reverted{background:#f0f1f4;color:#737b88}.meta{font-size:.8rem;margin:.55rem 0}.adjustments{border-top:1px solid #edf0f4;padding-top:.65rem}.adjustment+.adjustment{margin-top:.7rem}.leg{display:flex;justify-content:space-between;gap:1rem;background:#f7f8fb;border-radius:7px;padding:.5rem .65rem;margin-top:.4rem;font-size:.8rem}.leg b{color:#4256b5;text-align:right}.pagination{display:flex;align-items:center;justify-content:center;gap:1rem;margin-top:1rem;color:#657084;font-size:.84rem}.leave-heading h3{margin:0 0 .3rem}.leave-form{display:grid;grid-template-columns:1.2fr 1fr .8fr .8fr auto;align-items:end;gap:.75rem;margin:1rem 0}.leave-form label{display:flex;flex-direction:column;gap:.35rem;font-size:.82rem;font-weight:600}.leave-form select,.leave-form input{width:100%;border:1px solid #ccd3df;border-radius:8px;padding:.62rem;background:#fff}.leave-list article{padding:.7rem 0;border-top:1px solid #edf0f4}.empty-state{display:grid;place-items:center;min-height:160px;color:#7b8597;border:1px dashed #d5dae4;border-radius:10px;padding:1.5rem}.empty-state.compact{min-height:80px}@media(max-width:900px){.leave-form{grid-template-columns:1fr 1fr}.leave-form .p-button{grid-column:1/-1}.leg{flex-direction:column;gap:.2rem}.leg b{text-align:left}}@media(max-width:600px){.page-heading,.leave-heading,.record-summary{flex-direction:column}.leave-form{grid-template-columns:1fr}.scope-tabs button{padding:.65rem}.pagination{justify-content:space-between;gap:.2rem}.leave-list article{align-items:flex-start}.panel{padding:1rem}}
.record-actions,.edit-actions{display:flex;align-items:center;gap:.35rem}.record-edit{display:grid;grid-template-columns:1fr 180px;gap:.7rem;padding:.8rem;margin:.6rem 0;background:#f7f8fb;border-radius:9px}.record-edit>label{display:flex;flex-direction:column;gap:.3rem;font-size:.82rem;font-weight:600}.record-edit select,.record-edit input[type=date]{width:100%;border:1px solid #ccd3df;border-radius:8px;padding:.58rem;background:#fff}.edit-periods{grid-column:1/-1;display:flex;flex-wrap:wrap;gap:.45rem}.edit-periods label{display:flex;align-items:center;gap:.25rem;font-size:.8rem}.edit-actions{grid-column:1/-1;justify-content:flex-end}
</style>
