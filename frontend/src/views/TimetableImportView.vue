<template>
  <section class="import-page">
    <header class="page-heading">
      <div>
        <h2>{{ $t('importCenter.title') }}</h2>
        <p>{{ $t('importCenter.description') }}</p>
      </div>
      <span class="revision">{{ $t('rescheduling.revision', { revision: timetable.revision ?? '-' }) }}</span>
    </header>

    <section class="panel import-panel">
      <h3>{{ $t('importCenter.baseTitle') }}</h3>
      <div v-if="can('timetable.upload')" class="import-steps">
        <fieldset class="import-step">
          <legend><span class="step-number">1</span>{{ $t('importCenter.scheduleType') }}</legend>
          <div class="step-card type-card">
            <div class="schedule-type-options">
              <label :class="['schedule-option', { active: scheduleType === 'normal' }]">
                <input v-model="scheduleType" class="sr-only" type="radio" value="normal" :disabled="Boolean(preview)" @change="resetUploadFields" />
                <i class="pi pi-calendar" aria-hidden="true"></i>
                <span>{{ $t('importCenter.normalType') }}</span>
              </label>
              <label :class="['schedule-option', { active: scheduleType === 'post_exam' }]">
                <input v-model="scheduleType" class="sr-only" type="radio" value="post_exam" :disabled="Boolean(preview)" @change="resetUploadFields" />
                <i class="pi pi-clock" aria-hidden="true"></i>
                <span>{{ $t('importCenter.postExamType') }}</span>
              </label>
            </div>
          </div>
        </fieldset>

        <fieldset class="import-step">
          <legend><span class="step-number">2</span>{{ $t('importCenter.uploadFiles') }}</legend>
          <div class="step-card upload-list">
            <label class="upload-row">
              <span class="file-format">{{ scheduleType === 'post_exam' ? 'XLSX' : 'XLS' }}</span>
              <span class="upload-copy"><strong>{{ $t(scheduleType === 'post_exam' ? 'importCenter.postExamClassFile' : 'importCenter.classFile') }}</strong><small>{{ classFile?.name || $t('importCenter.noFileSelected') }}</small></span>
              <span class="upload-action">{{ $t('importCenter.chooseFile') }}</span>
              <input :key="`class-${uploadInputKey}`" class="sr-only" type="file" :accept="scheduleType === 'post_exam' ? '.xlsx' : '.xls'" @click="$event.target.value = null" @change="classFile = $event.target.files[0]" />
            </label>
            <label class="upload-row">
              <span class="file-format">XLSX</span>
              <span class="upload-copy"><strong>{{ $t('importCenter.teacherFile') }}</strong><small>{{ teacherFile?.name || $t('importCenter.noFileSelected') }}</small></span>
              <span class="upload-action">{{ $t('importCenter.chooseFile') }}</span>
              <input :key="`teacher-${uploadInputKey}`" class="sr-only" type="file" accept=".xlsx" @click="$event.target.value = null" @change="teacherFile = $event.target.files[0]" />
            </label>
            <label v-if="isAdmin && scheduleType !== 'post_exam'" class="upload-row optional">
              <span class="file-format docx">DOCX</span>
              <span class="upload-copy"><strong>{{ $t('importCenter.calendarFile') }}</strong><small>{{ calendarFile?.name || $t('importCenter.noFileSelected') }}</small></span>
              <span class="upload-action">{{ $t('importCenter.chooseFile') }}</span>
              <input :key="`calendar-${uploadInputKey}`" class="sr-only" type="file" accept=".docx" @click="$event.target.value = null" @change="calendarFile = $event.target.files[0]" />
            </label>
          </div>
        </fieldset>

        <fieldset class="import-step">
          <legend><span class="step-number">3</span>{{ $t(scheduleType === 'post_exam' ? 'importCenter.effectiveRanges' : 'importCenter.setDates') }}</legend>
          <div class="step-card date-fields">
            <TimetableRangeEditor v-if="scheduleType === 'post_exam'" v-model="effectiveRanges" compact :disabled="busy === 'activate'" />
            <template v-else>
            <label>{{ $t('importCenter.effectiveFrom') }}<input v-model="effectiveFrom" type="date" /></label>
            <label>{{ $t('importCenter.effectiveTo') }}<input v-model="effectiveTo" type="date" /></label>
            </template>
          </div>
        </fieldset>
      </div>
      <div class="import-footer">
        <p v-if="timetable.active" class="current-files"><i class="pi pi-info-circle" aria-hidden="true"></i>{{ $t('importCenter.currentFiles', { date: timetable.query_date, classFile: timetable.class_filename, teacherFile: timetable.teacher_filename }) }}</p>
        <p v-else class="notice warning">{{ $t('importCenter.noCurrent') }}</p>
        <Button v-if="can('timetable.upload')" :label="$t('importCenter.check')" icon="pi pi-search" class="progress-fill-button" :class="{ 'is-progressing': busy === 'preview' }" :loading="busy === 'preview'" :disabled="!filesReady || (!calendarFile && !importDatesValid)" @click="previewImport" />
      </div>
    </section>

    <section class="panel versions-panel">
      <div class="result-heading">
        <div><h3>{{ $t('importCenter.versionsTitle') }}</h3><p class="muted versions-intro">{{ $t('importCenter.versionsSummary') }}</p></div>
        <Button v-if="can('timetable.manage')" :label="$t('importCenter.groups.add')" icon="pi pi-plus" size="small" outlined :disabled="groupBusy" @click="openGroupEditor()" />
      </div>
      <p v-if="groupNotice" class="notice" :class="groupError ? 'danger' : 'success'" :role="groupError ? 'alert' : 'status'">{{ groupNotice }}</p>
      <div class="group-layout">
        <nav class="group-sidebar" :aria-label="$t('importCenter.groups.title')">
          <h4>{{ $t('importCenter.groups.title') }}</h4>
          <button v-for="group in groupEntries" :key="String(group.id)" type="button" class="group-link"
            :class="{ selected: selectedGroup === group.id, 'drop-target': dropGroup === group.id && draggedVersion !== null }"
            :aria-current="selectedGroup === group.id ? 'true' : undefined"
            @click="selectedGroup = group.id" @dragover="dragOverGroup($event, group.id)" @dragleave="leaveGroup($event)" @drop="dropIntoGroup($event, group.id)">
            <i :class="['pi', group.id === 'all' ? 'pi-th-large' : group.id === null ? 'pi-inbox' : 'pi-folder']" aria-hidden="true"></i>
            <span class="group-name">{{ group.name }}</span><span class="group-count">{{ group.count }}</span>
            <span v-if="group.dirty" class="group-unsaved" :title="$t('importCenter.unsaved')" :aria-label="$t('importCenter.unsaved')">•</span>
          </button>
          <p v-if="can('timetable.manage')" class="group-hint">{{ draggedVersion !== null ? $t('importCenter.groups.dropHint') : $t('importCenter.groups.hint') }}</p>
        </nav>
        <div class="group-content" :aria-busy="groupBusy">
          <div class="group-heading">
            <div><h4>{{ selectedGroupName }}</h4><span class="muted">{{ $t('importCenter.groups.count', { count: visibleVersions.length }) }}</span></div>
            <Button v-if="can('timetable.manage') && selectedGroup !== null && selectedGroup !== 'all'" :label="$t('importCenter.groups.rename')" icon="pi pi-pencil" size="small" text :disabled="groupBusy" @click="openGroupEditor(groups.find(group => group.id === selectedGroup))" />
          </div>
      <div class="table-wrap">
        <table class="versions-table">
          <thead><tr><th scope="col">{{ $t('importCenter.timetable') }}</th><th scope="col">{{ $t('importCenter.dateRange') }}</th><th scope="col">{{ $t('importCenter.scale') }}</th><th scope="col">{{ $t('importCenter.actions') }}</th></tr></thead>
          <tbody>
            <template v-for="version in visibleVersions" :key="version.id">
            <tr class="version-summary" :class="{ 'version-dirty': versionChanged(version), 'version-dragging': draggedVersion === version.id, 'version-expanded': expandedVersionId === version.id }">
              <td class="version-name-cell">
                <div class="version-identity">
                  <span v-if="can('timetable.manage')" class="drag-handle" :draggable="!groupBusy" role="img" :aria-label="$t('importCenter.groups.drag')" :title="$t('importCenter.groups.drag')" @dragstart="startVersionDrag($event, version)" @dragend="endVersionDrag">⠿</span>
                  <div class="version-name">
                    <strong :title="version.class_filename">{{ version.class_filename.replace(/\.[^.]+$/, '') }}</strong>
                    <div class="version-meta"><span>{{ $t(version.post_exam ? 'importCenter.postExamType' : 'importCenter.normalType') }}</span><span v-if="version.is_current" class="status current">{{ $t('importCenter.current') }}</span><span v-if="versionChanged(version)" class="draft-indicator">{{ $t('importCenter.unsaved') }}</span></div>
                  </div>
                </div>
              </td>
              <td :data-label="$t('importCenter.dateRange')">
                <div class="version-date-summary" :title="rangesText(versionDraftRanges(version))">
                  <span v-for="(range, index) in sortedRanges(versionDraftRanges(version)).slice(0, 2)" :key="index">{{ range.effective_from || '—' }} <span class="date-separator">→</span> {{ range.effective_to || $t('importCenter.ongoing') }}</span>
                  <span v-if="versionDraftRanges(version).length > 2" class="muted">{{ $t('importCenter.moreRanges', { count: versionDraftRanges(version).length - 2 }) }}</span>
                </div>
              </td>
              <td :data-label="$t('importCenter.scale')">
                <div class="version-stats"><span>{{ $t('importCenter.scaleValue', { lessons: version.lessons, teachers: version.teachers }) }}</span><small>{{ version.absence_records || version.adjustment_records ? $t('importCenter.recordValue', { absences: version.absence_records, adjustments: version.adjustment_records }) : $t('importCenter.noLinkedRecords') }}</small></div>
              </td>
              <td class="version-action-cell">
                <div class="version-actions">
                  <Button :id="`version-toggle-${version.id}`" :label="$t(expandedVersionId === version.id ? 'importCenter.collapse' : can('timetable.manage') ? 'common.edit' : 'importCenter.details')" :icon="expandedVersionId === version.id ? 'pi pi-angle-up' : undefined" size="small" :outlined="expandedVersionId !== version.id" :aria-expanded="expandedVersionId === version.id" :aria-controls="`version-editor-${version.id}`" :disabled="busy.startsWith('version-')" @click="toggleVersion(version)" />
                  <label v-if="can('timetable.manage')" class="move-group-label"><span class="sr-only">{{ $t('importCenter.groups.move') }}</span>
                    <select value="move" :aria-label="$t('importCenter.groups.moveVersion', { name: version.class_filename })" :disabled="groupBusy || busy.startsWith('version-')" @change="selectVersionGroup($event, version)">
                      <option value="move" disabled>{{ $t('importCenter.groups.move') }}</option>
                      <option value="" :disabled="version.group_id === null">{{ $t('importCenter.groups.ungrouped') }}</option>
                      <option v-for="group in groups" :key="group.id" :value="group.id" :disabled="version.group_id === group.id">{{ group.name }}</option>
                    </select>
                  </label>
                </div>
              </td>
            </tr>
            <tr v-if="expandedVersionId === version.id" class="version-editor-row">
              <td colspan="4">
                <section :id="`version-editor-${version.id}`" class="version-editor" :aria-labelledby="`version-editor-title-${version.id}`">
                  <div class="editor-heading"><h5 :id="`version-editor-title-${version.id}`">{{ $t(can('timetable.manage') ? 'importCenter.editTimetable' : 'importCenter.details') }}</h5><span v-if="versionChanged(version)" class="status unsaved">{{ $t('importCenter.unsaved') }}</span></div>
                  <div class="version-range-editor">
                    <TimetableRangeEditor v-if="version.post_exam" v-model="version.draft_effective_ranges" :disabled="!can('timetable.manage') || busy === `version-${version.id}`" @update:model-value="message = ''" />
                    <template v-else>
                      <label><span>{{ $t('importCenter.startDate') }}</span><input v-model="version.draft_effective_from" type="date" :disabled="!can('timetable.manage') || busy === `version-${version.id}`" @input="message = ''" /></label>
                      <label><span>{{ $t('importCenter.endDate') }}</span><input v-model="version.draft_effective_to" type="date" :disabled="!can('timetable.manage') || busy === `version-${version.id}`" @input="message = ''" /></label>
                      <p v-if="!rangesValid(versionDraftRanges(version))" class="range-validation" role="status">{{ $t(rangeErrors(versionDraftRanges(version))[0]) }}</p>
                    </template>
                  </div>
                  <fieldset class="version-specials" :disabled="!can('timetable.manage') || busy === `version-${version.id}`">
                    <legend>{{ $t('importCenter.specialSubjects') }} <span class="muted">({{ version.draft_special_subjects.length }})</span></legend>
                    <div><label v-for="subject in version.subjects" :key="subject" :class="{ selected: version.draft_special_subjects.includes(subject) }"><input v-model="version.draft_special_subjects" type="checkbox" :value="subject" @change="message = ''" />{{ subject }}</label></div>
                  </fieldset>
                  <div class="version-source-files">
                    <h5>{{ $t('importCenter.files') }}</h5>
                    <div><p><i class="pi pi-file-excel" aria-hidden="true"></i><span><small>{{ $t('importCenter.classWorkbook') }}</small>{{ version.class_filename }}</span></p><p><i class="pi pi-file-excel" aria-hidden="true"></i><span><small>{{ $t('importCenter.teacherWorkbook') }}</small>{{ version.teacher_filename }}</span></p></div>
                  </div>
                  <p class="editor-hint">{{ $t('importCenter.versionsHint') }}</p>
                  <p v-if="versionSaveError" class="notice danger" role="alert">{{ versionSaveError }}</p>
                  <div v-if="can('timetable.manage')" class="version-editor-footer">
                    <div class="version-delete"><Button :label="$t('common.delete')" icon="pi pi-trash" size="small" severity="danger" text :disabled="version.locked || groupBusy || busy.startsWith('version-')" @click="removeVersion(version)" /><small v-if="version.locked"><i class="pi pi-lock" aria-hidden="true"></i>{{ $t('importCenter.linkedDeleteHint') }}</small></div>
                    <div class="version-save-actions"><Button :label="$t('importCenter.cancelChanges')" size="small" outlined :disabled="busy === `version-${version.id}`" @click="cancelVersion(version)" /><Button :label="$t('importCenter.saveChanges')" size="small" :loading="busy === `version-${version.id}`" :disabled="!versionChanged(version) || !rangesValid(versionDraftRanges(version))" @click="saveVersion(version)" /></div>
                  </div>
                </section>
              </td>
            </tr>
            </template>
            <tr v-if="!visibleVersions.length"><td colspan="4" class="empty-row">{{ versions.length ? $t('importCenter.groups.empty') : $t('importCenter.noVersions') }}</td></tr>
          </tbody>
        </table>
      </div>
        </div>
      </div>
    </section>

    <Dialog v-model:visible="groupDialogVisible" modal class="timetable-group-dialog" :draggable="false" :pt="{ root: { 'aria-labelledby': 'timetable-group-title' } }" :closable="!groupBusy" :close-on-escape="!groupBusy">
      <template #header>
        <div class="group-dialog-heading">
          <span class="group-dialog-icon"><i class="pi pi-folder" aria-hidden="true"></i></span>
          <div><h3 id="timetable-group-title">{{ $t(editingGroupId === null ? 'importCenter.groups.add' : 'importCenter.groups.rename') }}</h3><p>{{ $t('importCenter.groups.dialogIntro') }}</p></div>
        </div>
      </template>
      <form class="group-form" @submit.prevent="saveGroup">
        <div class="group-name-field">
          <label for="timetable-group-name">{{ $t('importCenter.groups.name') }}</label>
          <input id="timetable-group-name" v-model="groupName" autofocus required maxlength="80" autocomplete="off" aria-describedby="timetable-group-hint timetable-group-error" :aria-invalid="Boolean(groupFormError)" :placeholder="$t('importCenter.groups.placeholder')" :disabled="groupBusy" @input="groupFormError = ''" />
        </div>
        <p id="timetable-group-hint" class="group-form-hint"><i class="pi pi-info-circle" aria-hidden="true"></i><span>{{ $t('importCenter.groups.nameHint') }}</span></p>
        <p v-if="groupFormError" id="timetable-group-error" class="notice danger" role="alert">{{ groupFormError }}</p>
        <div class="group-form-actions"><Button :label="$t('common.cancel')" text :disabled="groupBusy" @click="groupDialogVisible = false" /><Button type="submit" :label="$t(editingGroupId === null ? 'importCenter.groups.create' : 'importCenter.saveChanges')" :icon="editingGroupId === null ? 'pi pi-plus' : 'pi pi-check'" :loading="groupBusy" :disabled="!groupName.trim()" /></div>
      </form>
    </Dialog>

    <Transition name="motion-fade">
    <div v-if="preview" class="preview-stack">
      <section class="summary-grid">
        <div><strong>{{ preview.classes }}</strong><span>{{ $t('importCenter.classes') }}</span></div>
        <div><strong>{{ preview.teachers }}</strong><span>{{ $t('importCenter.teachers') }}</span></div>
        <div><strong>{{ preview.lessons }}</strong><span>{{ $t('importCenter.lessons') }}</span></div>
        <div :class="{ alert: preview.blocked_lessons }"><strong>{{ preview.blocked_lessons }}</strong><span>{{ $t('importCenter.blocked') }}</span></div>
      </section>

      <section class="panel">
        <div class="result-heading">
          <div><h3>{{ $t('importCenter.resultTitle') }}</h3><p class="muted">{{ $t('importCenter.resultHint') }}</p></div>
          <div class="result-actions">
            <Button v-if="can('timetable.upload')" :label="$t('importCenter.cancelUpload')" severity="danger" text :loading="busy === 'discard'" @click="discardPreview" />
            <Button v-if="can('timetable.manage')" :label="$t('importCenter.activate')" icon="pi pi-check" severity="success" :loading="busy === 'activate'" :disabled="hasErrors || hasUnresolvedReviews || calendarNeedsReview || !importDatesValid" @click="activateImport" />
          </div>
        </div>
        <div v-if="scheduleType === 'post_exam'" class="preview-ranges">
          <strong>{{ $t('importCenter.effectiveRanges') }}</strong>
          <ul><li v-for="(range, index) in sortedRanges(effectiveRanges)" :key="index">{{ range.effective_from || '—' }} → {{ range.effective_to || '—' }}</li></ul>
        </div>
        <div v-if="preview.calendar" :class="['calendar-review-status', { confirmed: calendarSelection }]">
          <i :class="calendarSelection ? 'pi pi-check-circle' : 'pi pi-calendar'" aria-hidden="true"></i>
          <div>
            <strong>{{ $t('importCenter.calendar.reviewStatusTitle') }}</strong>
            <span>{{ calendarSelection ? $t('importCenter.calendar.reviewConfirmed', { count: calendarSelection.calendar_closures.length }) : $t('importCenter.calendar.reviewRequired') }}</span>
          </div>
          <Button :label="$t(calendarSelection ? 'importCenter.calendar.reviewAgain' : 'importCenter.calendar.reviewNow')" size="small" outlined @click="calendarDialogVisible = true" />
        </div>
        <fieldset class="special-subjects">
          <legend>{{ $t('importCenter.specialSubjects') }}</legend>
          <p class="muted">{{ $t('importCenter.specialSubjectsHint') }}</p>
          <div>
            <label v-for="subject in preview.subjects" :key="subject" :class="{ selected: specialSubjects.includes(subject) }">
              <input v-model="specialSubjects" type="checkbox" :value="subject" :disabled="!can('timetable.manage')" />{{ subject }}
            </label>
          </div>
        </fieldset>
        <TransitionGroup v-if="preview.warnings.length" name="motion-list" tag="ul" class="warnings">
          <li v-for="warning in preview.warnings" :key="warning">{{ warning }}</li>
        </TransitionGroup>
        <p v-if="hasErrors" class="notice danger">{{ $t('importCenter.errorsBlock') }}</p>
        <p v-else-if="hasUnresolvedReviews" class="notice warning">{{ $t('importCenter.reviewsProgress', { confirmed: confirmedReviewCount, total: reviewIds.length, remaining: unresolvedReviewCount }) }}</p>
        <div v-if="can('timetable.upload') && reviewIds.length" class="bulk-actions">
          <label><input type="checkbox" :checked="allReviewsSelected" @change="toggleAllReviews" />{{ $t('importCenter.selectAllReviews') }}</label>
          <span>{{ $t('importCenter.selectedReviews', { count: selectedReviewIds.length }) }}</span>
          <Button :label="$t('importCenter.clearSelection')" text size="small" :disabled="!selectedReviewIds.length" @click="selectedReviewIds = []" />
          <Button :label="bulkClassLabel" size="small" outlined :disabled="!selectedReviewIds.length" @click="applyBulk('class')" />
          <Button :label="bulkTeacherLabel" size="small" :disabled="!selectedReviewIds.length" @click="applyBulk('teacher')" />
          <Button :label="$t('importCenter.confirmSelected')" icon="pi pi-check" severity="success" size="small" :loading="busy === 'save-selected'" :disabled="!canConfirmSelected" @click="saveResolutions(selectedReviewIds, 'save-selected')" />
        </div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>{{ $t('importCenter.selectReview') }}</th><th>{{ $t('importCenter.severity') }}</th><th>{{ $t('importCenter.weekdayPeriod') }}</th><th>{{ $t('rescheduling.class') }}</th><th>{{ $t('rescheduling.subject') }}</th><th>{{ $t('rescheduling.teacherColumn') }}</th><th>{{ $t('importCenter.classWorkbook') }}</th><th>{{ $t('importCenter.teacherWorkbook') }}</th><th>{{ $t('importCenter.decision') }}</th></tr></thead>
            <TransitionGroup name="motion-list" tag="tbody">
              <tr v-for="(issue, index) in preview.issues" :key="issue.resolution_id || index">
                <td><input v-if="can('timetable.upload') && issue.severity === 'review'" v-model="selectedReviewIds" type="checkbox" :value="resolutionId(issue)" /></td>
                <td><span :class="['status', issue.severity]">{{ issue.severity === 'error' ? $t('common.error') : $t('importCenter.review') }}</span></td>
                <td>{{ weekdayLabel(issue.weekday) }} {{ $t('records.period', { period: issue.period }) }}</td>
                <td>{{ issue.class_code }}</td><td>{{ issue.subject }}</td><td>{{ issue.teacher || '-' }}</td>
                <td>{{ issue.class_workbook }}</td><td>{{ issue.teacher_workbook }}</td>
                <td>
                  <div v-if="issue.severity === 'review'" class="resolution-cell">
                    <div class="resolution-choice">
                      <label :class="{ selected: resolutions[resolutionId(issue)] === 'class' }"><input v-model="resolutions[resolutionId(issue)]" type="radio" :name="resolutionId(issue)" value="class" :disabled="!can('timetable.upload')" />{{ $t(issue.code === 'teacher_extra_assignment' ? 'importCenter.ignoreExtraTeacher' : 'importCenter.useClassWorkbook') }}</label>
                      <label :class="{ selected: resolutions[resolutionId(issue)] === 'teacher' }"><input v-model="resolutions[resolutionId(issue)]" type="radio" :name="resolutionId(issue)" value="teacher" :disabled="!can('timetable.upload')" />{{ $t(issue.code === 'teacher_extra_assignment' ? 'importCenter.addCoTeacher' : 'importCenter.useTeacherWorkbook') }}</label>
                    </div>
                    <Button
                      v-if="can('timetable.upload')"
                      :label="$t(isResolutionConfirmed(issue) ? 'importCenter.confirmedDecision' : 'importCenter.confirmThisDecision')"
                      icon="pi pi-check"
                      size="small"
                      :outlined="!isResolutionConfirmed(issue)"
                      :severity="isResolutionConfirmed(issue) ? 'success' : undefined"
                      :loading="busy === `resolution-${resolutionId(issue)}`"
                      :disabled="!resolutions[resolutionId(issue)] || isResolutionConfirmed(issue)"
                      @click="saveResolutions([resolutionId(issue)], `resolution-${resolutionId(issue)}`)"
                    />
                  </div>
                  <span v-else class="muted">{{ $t('importCenter.fixSource') }}</span>
                </td>
              </tr>
              <tr v-if="!preview.issues.length"><td colspan="9" class="empty-row">{{ $t('importCenter.perfectMatch') }}</td></tr>
            </TransitionGroup>
          </table>
        </div>
      </section>
    </div>
    </Transition>

    <CalendarImportPreviewDialog
      v-if="preview?.calendar"
      :visible="calendarDialogVisible"
      :calendar="preview.calendar"
      :effective-from="effectiveFrom"
      :effective-to="effectiveTo"
      :initial-phase="scheduleType === 'normal' ? 'full_year' : 'custom'"
      @cancel="calendarDialogVisible = false"
      @confirm="confirmCalendar"
    />

    <Transition name="motion-fade"><p v-if="message" class="notice success">{{ message }}</p></Transition>
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import axios from 'axios'
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import CalendarImportPreviewDialog from '../components/CalendarImportPreviewDialog.vue'
import TimetableRangeEditor from '../components/TimetableRangeEditor.vue'
import { rangeErrors, rangesValid, sortedRanges } from '../components/timetableRanges'

const { t } = useI18n()
const props = defineProps({ can: { type: Function, required: true }, isAdmin: { type: Boolean, default: false } })

const timetable = ref({ active: false })
const versions = ref([])
const expandedVersionId = ref(null)
const versionSaveError = ref('')
const toggleVersion = (version) => {
  expandedVersionId.value = expandedVersionId.value === version.id ? null : version.id
  versionSaveError.value = ''
}
const closeVersion = async (version) => {
  expandedVersionId.value = null
  await nextTick()
  document.getElementById(`version-toggle-${version.id}`)?.focus({ preventScroll: true })
}
const cancelVersion = (version) => {
  resetVersion(version)
  versionSaveError.value = ''
  closeVersion(version)
}
const groups = ref([])
const selectedGroup = ref(null)
const groupsLoaded = ref(false)
const groupBusy = ref(false)
const groupNotice = ref('')
const groupError = ref(false)
const groupDialogVisible = ref(false)
const editingGroupId = ref(null)
const groupName = ref('')
const groupFormError = ref('')
const draggedVersion = ref(null)
const dropGroup = ref(undefined)
const groupEntries = computed(() => [
  { id: 'all', name: t('importCenter.groups.all') },
  { id: null, name: t('importCenter.groups.ungrouped') },
  ...groups.value
].map(group => {
  const rows = versions.value.filter(version => group.id === 'all' || version.group_id === group.id)
  return { ...group, count: rows.length, dirty: rows.some(versionChanged) }
}))
const visibleVersions = computed(() => versions.value.filter(version => selectedGroup.value === 'all' || version.group_id === selectedGroup.value))
const selectedGroupName = computed(() => groupEntries.value.find(group => group.id === selectedGroup.value)?.name || '')

const openGroupEditor = (group) => {
  editingGroupId.value = group?.id ?? null
  groupName.value = group?.name || ''
  groupFormError.value = ''
  groupDialogVisible.value = true
}
const saveGroup = async () => {
  if (groupBusy.value || !groupName.value.trim()) return
  groupBusy.value = true; groupFormError.value = ''
  try {
    const payload = { name: groupName.value.trim() }
    const { data } = editingGroupId.value === null
      ? await axios.post('/api/timetable-groups', payload, { _silent: true })
      : await axios.put(`/api/timetable-groups/${editingGroupId.value}`, payload, { _silent: true })
    groups.value = [...groups.value.filter(group => group.id !== data.id), data].sort((left, right) => right.name.localeCompare(left.name))
    selectedGroup.value = data.id
    groupDialogVisible.value = false
  } catch (error) {
    groupFormError.value = typeof error.response?.data?.detail === 'string' ? error.response.data.detail : t('importCenter.groups.saveFailed')
  } finally { groupBusy.value = false }
}
const moveVersion = async (version, groupId) => {
  if (!props.can('timetable.manage') || groupBusy.value || version.group_id === groupId) return
  groupBusy.value = true; groupNotice.value = ''; groupError.value = false
  try {
    await axios.put(`/api/timetables/${version.id}/group`, { group_id: groupId }, { _silent: true })
    version.group_id = groupId
    groupNotice.value = t('importCenter.groups.moved', { name: groupEntries.value.find(group => group.id === groupId)?.name })
  } catch (error) {
    groupError.value = true
    groupNotice.value = typeof error.response?.data?.detail === 'string' ? error.response.data.detail : t('importCenter.groups.moveFailed')
  } finally { groupBusy.value = false }
}
const selectVersionGroup = (event, version) => {
  const groupId = event.target.value ? Number(event.target.value) : null
  event.target.value = 'move'
  return moveVersion(version, groupId)
}
const startVersionDrag = (event, version) => {
  if (groupBusy.value || !props.can('timetable.manage')) { event.preventDefault(); return }
  draggedVersion.value = version.id
  event.dataTransfer.effectAllowed = 'move'
  event.dataTransfer.setData('text/plain', String(version.id))
}
const endVersionDrag = () => { draggedVersion.value = null; dropGroup.value = undefined }
const dragOverGroup = (event, groupId) => {
  if (draggedVersion.value === null || groupId === 'all' || groupBusy.value) return
  event.preventDefault()
  event.dataTransfer.dropEffect = 'move'
  dropGroup.value = groupId
}
const leaveGroup = (event) => {
  if (!event.currentTarget.contains(event.relatedTarget)) dropGroup.value = undefined
}
const dropIntoGroup = (event, groupId) => {
  event.preventDefault()
  const version = versions.value.find(row => row.id === draggedVersion.value)
  endVersionDrag()
  if (version && groupId !== 'all') return moveVersion(version, groupId)
}
const scheduleType = ref('normal')
const classFile = ref(null)
const teacherFile = ref(null)
const calendarFile = ref(null)
const effectiveFrom = ref('')
const effectiveTo = ref('')
const effectiveRanges = ref([{ effective_from: '', effective_to: '' }])
const importRanges = computed(() => scheduleType.value === 'post_exam' ? effectiveRanges.value
  : [{ effective_from: effectiveFrom.value, effective_to: effectiveTo.value }])
const importDatesValid = computed(() => rangesValid(importRanges.value))
const rangesText = (ranges) => sortedRanges(ranges).map(range => `${range.effective_from} → ${range.effective_to}`).join('；')
const preview = ref(null)
const calendarDialogVisible = ref(false)
const calendarSelection = ref(null)
const busy = ref('')
const message = ref('')
const resolutions = ref({})
const savedResolutions = ref({})
const selectedReviewIds = ref([])
const specialSubjects = ref([])
const uploadInputKey = ref(0)
const resetUploadFields = () => {
  classFile.value = null
  teacherFile.value = null
  calendarFile.value = null
  uploadInputKey.value += 1
}
const resolutionId = (issue) => issue.resolution_id || `${issue.weekday}:${issue.period}:${issue.class_code}:${issue.teacher}`
const reviewIds = computed(() => (preview.value?.issues || [])
  .filter(issue => issue.severity === 'review')
  .map(resolutionId))
const filesReady = computed(() => Boolean(classFile.value && teacherFile.value))
const calendarNeedsReview = computed(() => Boolean(preview.value?.calendar && !calendarSelection.value))
const allReviewsSelected = computed(() => reviewIds.value.length > 0 && selectedReviewIds.value.length === reviewIds.value.length)
const hasErrors = computed(() => preview.value?.issues.some(issue => issue.severity === 'error'))
const isResolutionConfirmed = (issue) => Boolean(savedResolutions.value[resolutionId(issue)])
  && savedResolutions.value[resolutionId(issue)] === resolutions.value[resolutionId(issue)]
const confirmedReviewCount = computed(() => (preview.value?.issues || []).filter(
  issue => issue.severity === 'review' && isResolutionConfirmed(issue)
).length)
const unresolvedReviewCount = computed(() => reviewIds.value.length - confirmedReviewCount.value)
const hasUnresolvedReviews = computed(() => unresolvedReviewCount.value > 0)
const selectedIssues = computed(() => (preview.value?.issues || []).filter(issue => selectedReviewIds.value.includes(resolutionId(issue))))
const selectedIssueType = computed(() => {
  if (!selectedIssues.value.length) return 'none'
  if (selectedIssues.value.every(issue => issue.code === 'teacher_extra_assignment')) return 'extra'
  if (selectedIssues.value.every(issue => issue.code !== 'teacher_extra_assignment')) return 'mismatch'
  return 'mixed'
})
const bulkClassLabel = computed(() => t(selectedIssueType.value === 'extra' ? 'importCenter.bulkIgnoreExtraTeacher'
  : selectedIssueType.value === 'mismatch' ? 'importCenter.bulkUseClassWorkbook' : 'importCenter.bulkLeftDecision'))
const bulkTeacherLabel = computed(() => t(selectedIssueType.value === 'extra' ? 'importCenter.bulkAddCoTeacher'
  : selectedIssueType.value === 'mismatch' ? 'importCenter.bulkUseTeacherWorkbook' : 'importCenter.bulkRightDecision'))
const canConfirmSelected = computed(() => selectedReviewIds.value.length > 0
  && selectedReviewIds.value.every(id => resolutions.value[id])
  && selectedReviewIds.value.some(id => savedResolutions.value[id] !== resolutions.value[id]))
const sameItems = (left, right) => left.length === right.length && left.every(item => right.includes(item))
const versionDraftRanges = (version) => version.post_exam ? version.draft_effective_ranges
  : [{ effective_from: version.draft_effective_from, effective_to: version.draft_effective_to }]
const versionChanged = (version) => JSON.stringify(sortedRanges(versionDraftRanges(version))) !== JSON.stringify(sortedRanges(version.effective_ranges))
  || !sameItems(version.draft_special_subjects, version.special_subjects)
const hasUnsavedVersions = computed(() => versions.value.some(versionChanged))

const resetVersion = (version) => {
  version.draft_effective_from = version.effective_from
  version.draft_effective_to = version.effective_to || ''
  version.draft_effective_ranges = version.effective_ranges.map(range => ({ ...range }))
  version.draft_special_subjects = [...version.special_subjects]
}
const resetAllVersions = () => versions.value.forEach(resetVersion)

const handleBeforeUnload = (event) => {
  if (!hasUnsavedVersions.value) return
  event.preventDefault()
  event.returnValue = ''
}

defineExpose({ hasUnsavedChanges: () => hasUnsavedVersions.value, resetUnsavedChanges: resetAllVersions })

const toggleAllReviews = (event) => {
  selectedReviewIds.value = event.target.checked ? [...reviewIds.value] : []
}
const applyBulk = (choice) => {
  resolutions.value = {
    ...resolutions.value,
    ...Object.fromEntries(selectedReviewIds.value.map(id => [id, choice]))
  }
}

const saveResolutions = async (ids, busyKey) => {
  const decisions = Object.fromEntries(ids
    .filter(id => resolutions.value[id])
    .map(id => [id, resolutions.value[id]]))
  if (!Object.keys(decisions).length) return
  busy.value = busyKey; message.value = ''
  try {
    const response = (await axios.put(`/api/timetables/import/${preview.value.preview_id}/resolutions`, {
      resolutions: decisions
    })).data
    savedResolutions.value = response.saved_resolutions
    message.value = response.remaining_count
      ? t('importCenter.progressSaved', { confirmed: response.confirmed_count, total: reviewIds.value.length, remaining: response.remaining_count })
      : t('importCenter.allDecisionsConfirmed')
  } finally { busy.value = '' }
}

const loadCurrent = async (savedVersionId) => {
  const [currentResponse, versionsResponse, groupsResponse] = await Promise.all([
    axios.get('/api/timetables/current'), axios.get('/api/timetables'), axios.get('/api/timetable-groups')
  ])
  timetable.value = currentResponse.data
  groups.value = groupsResponse.data
  versions.value = versionsResponse.data.map(version => {
    const previous = versions.value.find(row => row.id === version.id)
    const row = {
      ...version,
      group_id: version.group_id ?? null,
      effective_ranges: (version.effective_ranges || [{ effective_from: version.effective_from, effective_to: version.effective_to }])
        .map(range => ({ ...range, effective_to: range.effective_to || '' }))
    }
    resetVersion(row)
    if (previous && previous.id !== savedVersionId && versionChanged(previous)) {
      row.draft_effective_from = previous.draft_effective_from
      row.draft_effective_to = previous.draft_effective_to
      row.draft_effective_ranges = previous.draft_effective_ranges
      row.draft_special_subjects = previous.draft_special_subjects
    }
    return row
  })
  if (!groupsLoaded.value) {
    selectedGroup.value = versions.value.find(version => version.is_current)?.group_id ?? null
    groupsLoaded.value = true
  }
}

const saveVersion = async (version) => {
  busy.value = `version-${version.id}`; message.value = ''; versionSaveError.value = ''
  try {
    await axios.put(`/api/timetables/${version.id}`, {
      ...(version.post_exam ? { effective_ranges: sortedRanges(version.draft_effective_ranges) }
        : { effective_from: version.draft_effective_from, effective_to: version.draft_effective_to }),
      special_subjects: version.draft_special_subjects
    }, { _silent: true })
    message.value = version.post_exam ? t('importCenter.rangesUpdated', { ranges: rangesText(version.draft_effective_ranges) }) : t('importCenter.versionUpdated', {
      start: version.draft_effective_from, end: version.draft_effective_to
    })
    await loadCurrent(version.id)
    busy.value = ''
    await closeVersion(version)
  } catch (error) {
    versionSaveError.value = typeof error.response?.data?.detail === 'string' ? error.response.data.detail : t('importCenter.versionSaveFailed')
  } finally { busy.value = '' }
}

const removeVersion = async (version) => {
  if (!window.confirm(t('importCenter.deleteConfirm', { date: version.post_exam ? rangesText(version.effective_ranges) : version.effective_from }))) return
  await axios.delete(`/api/timetables/${version.id}`)
  message.value = t('importCenter.versionDeleted')
  await loadCurrent()
}

const previewImport = async () => {
  busy.value = 'preview'; message.value = ''
  try {
    const form = new FormData()
    form.append('schedule_type', scheduleType.value)
    form.append('class_workbook', classFile.value)
    form.append('teacher_workbook', teacherFile.value)
    if (calendarFile.value) form.append('calendar_docx', calendarFile.value)
    preview.value = (await axios.post('/api/timetables/import/preview', form)).data
    calendarSelection.value = null
    calendarDialogVisible.value = Boolean(preview.value.calendar)
    specialSubjects.value = preview.value.subjects.filter(subject => /體育|視藝|美術|中默|英默|默書|默寫|聽寫|P\.?E\.?/i.test(subject))
    resolutions.value = {}
    savedResolutions.value = {}
    selectedReviewIds.value = []
  } finally { busy.value = '' }
}

const activateImport = async () => {
  busy.value = 'activate'; message.value = ''
  try {
    await axios.post(`/api/timetables/import/${preview.value.preview_id}/activate`, {
      ...(scheduleType.value === 'post_exam' ? { effective_ranges: sortedRanges(effectiveRanges.value) }
        : { effective_from: effectiveFrom.value, effective_to: effectiveTo.value }),
      resolutions: resolutions.value, special_subjects: specialSubjects.value,
      calendar_closures: calendarSelection.value?.calendar_closures || []
    })
    message.value = scheduleType.value === 'post_exam' ? t('importCenter.rangesActivated', { ranges: rangesText(effectiveRanges.value) })
      : t('importCenter.activated', { start: effectiveFrom.value, end: effectiveTo.value })
    preview.value = null
    resolutions.value = {}
    savedResolutions.value = {}
    selectedReviewIds.value = []
    specialSubjects.value = []
    calendarSelection.value = null
    calendarDialogVisible.value = false
    selectedGroup.value = null
    await loadCurrent()
  } finally { busy.value = '' }
}

const discardPreview = async () => {
  busy.value = 'discard'; message.value = ''
  try {
    await axios.delete(`/api/timetables/import/${preview.value.preview_id}`)
    preview.value = null
    classFile.value = null
    teacherFile.value = null
    calendarFile.value = null
    resolutions.value = {}
    savedResolutions.value = {}
    selectedReviewIds.value = []
    specialSubjects.value = []
    calendarSelection.value = null
    calendarDialogVisible.value = false
    uploadInputKey.value += 1
    message.value = t('importCenter.uploadCancelled')
  } finally { busy.value = '' }
}

const weekdayLabel = (weekday) => t(`importCenter.weekdays.${weekday}`, `${weekday}`)
const confirmCalendar = (selection) => {
  calendarSelection.value = selection
  effectiveFrom.value = selection.effective_from
  effectiveTo.value = selection.effective_to
  calendarDialogVisible.value = false
}

onMounted(() => {
  window.addEventListener('beforeunload', handleBeforeUnload)
  loadCurrent()
})
onBeforeUnmount(() => window.removeEventListener('beforeunload', handleBeforeUnload))
</script>

<style scoped>
.import-page { display: grid; gap: 1.25rem; color: var(--text-color-primary); }
.page-heading, .result-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 1.5rem; }
.result-actions { display: flex; align-items: center; gap: .45rem; }
.page-heading h2 { margin: 0 0 .35rem; font-size: clamp(1.65rem, 3vw, 2.15rem); line-height: 1.15; letter-spacing: -.035em; }
.page-heading p, .muted { color: var(--text-color-secondary); }
.revision { padding-top: .4rem; color: var(--text-color-secondary); font-size: var(--font-supporting); white-space: nowrap; }
.special-subjects { margin: 1rem 0; padding: 1rem; border: 1px solid var(--border-color); border-radius: 10px; }
.special-subjects legend { padding: 0 .35rem; font-size: var(--font-data); font-weight: 700; }
.special-subjects p { margin: 0 0 .65rem; font-size: var(--font-supporting); }
.special-subjects > div { display: flex; flex-wrap: wrap; gap: .45rem; }
.special-subjects label { display: flex; align-items: center; gap: .35rem; padding: .42rem .6rem; border: 1px solid var(--border-color); border-radius: 7px; cursor: pointer; font-size: var(--font-ui); }
.special-subjects label.selected { border-color: #d3aa52; background: #fff6db; color: #72500b; }
.panel { min-width: 0; padding: 1.25rem; border: 1px solid var(--border-color); border-radius: var(--radius-lg); background: var(--card-background); box-shadow: var(--shadow-panel); }
.preview-stack { display: grid; gap: 1.25rem; }
.panel h3 { margin: 0 0 .9rem; }
.result-heading h3 { margin: 0; }
.import-panel { padding: 1.5rem; }
.import-steps { position: relative; display: grid; grid-template-columns: minmax(180px, .72fr) minmax(420px, 1.55fr) minmax(280px, 1fr); gap: 1rem; }
.import-steps::before { position: absolute; top: 1rem; right: 1.25rem; left: 1.25rem; height: 1px; background: #dce3eb; content: ''; }
.import-step { min-width: 0; margin: 0; padding: 0; border: 0; }
.import-step legend { position: relative; z-index: 1; display: flex; align-items: center; gap: .55rem; margin: 0 0 .75rem; padding: 0 .7rem 0 0; background: var(--card-background); color: #25364d; font-size: var(--font-ui); font-weight: 750; }
.step-number { display: inline-grid; width: 2rem; height: 2rem; flex: 0 0 2rem; place-items: center; border-radius: 50%; background: var(--primary-color); color: #fff; font-size: .88rem; }
.step-card { height: calc(100% - 2.75rem); min-height: 9rem; padding: .9rem; border: 1px solid #dce3eb; border-radius: 12px; background: #fbfcfe; }
.type-card { display: grid; align-items: center; }
.schedule-type-options { display: grid; grid-template-columns: 1fr 1fr; gap: .55rem; }
.schedule-option { display: grid; min-height: 5.4rem; place-items: center; gap: .3rem; padding: .75rem .45rem; border: 1px solid #d5dde7; border-radius: 10px; background: #fff; color: var(--text-color-secondary); cursor: pointer; font-size: var(--font-ui); font-weight: 700; text-align: center; transition: border-color .16s ease, background .16s ease, color .16s ease, box-shadow .16s ease; }
.schedule-option i { font-size: 1.2rem; }
.schedule-option:hover { border-color: #aebdce; }
.schedule-option.active { border-color: var(--primary-color); background: var(--highlight-bg); color: var(--primary-color-dark); box-shadow: inset 0 0 0 1px var(--primary-color); }
.schedule-option:has(input:focus-visible) { outline: 3px solid color-mix(in srgb, var(--primary-color) 24%, transparent); outline-offset: 2px; }
.schedule-option:has(input:disabled) { cursor: not-allowed; opacity: .7; }
.upload-list { display: grid; align-content: center; gap: .55rem; }
.upload-row { position: relative; display: grid; grid-template-columns: 3.2rem minmax(0, 1fr) auto; align-items: center; gap: .7rem; min-height: 3.45rem; padding: .55rem .65rem; border: 1px solid #dce3eb; border-radius: 9px; background: #fff; cursor: pointer; }
.upload-row:hover { border-color: #aebdce; background: #f8fafc; }
.upload-row:has(input:focus-visible) { outline: 3px solid color-mix(in srgb, var(--primary-color) 24%, transparent); outline-offset: 1px; }
.file-format { display: inline-grid; min-height: 1.85rem; place-items: center; border-radius: 6px; background: #e6f4ea; color: #267147; font-size: .66rem; font-weight: 800; letter-spacing: .03em; }
.file-format.docx { background: #e8eff9; color: #315e8b; }
.upload-copy { display: grid; min-width: 0; gap: .08rem; }
.upload-copy strong, .upload-copy small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.upload-copy strong { color: #344054; font-size: var(--font-supporting); }
.upload-copy small { color: var(--text-color-secondary); font-size: .76rem; font-weight: 500; }
.upload-action { padding: .35rem .55rem; border: 1px solid #ccd6e2; border-radius: 7px; color: var(--primary-color-dark); font-size: var(--font-supporting); font-weight: 700; white-space: nowrap; }
.date-fields { display: grid; align-content: center; gap: .75rem; }
.date-fields label { display: grid; gap: .32rem; color: #344054; font-size: var(--font-supporting); font-weight: 700; }
.import-footer { display: flex; align-items: center; gap: 1rem; margin-top: 1rem; padding: .75rem .8rem .75rem 1rem; border-radius: 10px; background: #eef5fa; }
.import-footer p { margin: 0; }
.current-files { display: flex; min-width: 0; align-items: center; gap: .55rem; margin-right: auto !important; color: #50657e; font-size: var(--font-supporting); }
.current-files i { color: var(--primary-color); }
.import-footer .notice { flex: 1; }
.import-footer .p-button { flex: 0 0 auto; min-height: 2.85rem; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
input { width: 100%; min-height: 2.55rem; padding: .6rem .7rem; border: 1px solid #cfd6df; border-radius: 8px; background: #fff; color: var(--text-color-primary); }
input:hover { border-color: #aeb8c5; }
input:focus { border-color: var(--primary-color); }
input[type=file] { padding: .45rem; }
input[type=checkbox] { width: auto; min-height: auto; accent-color: var(--primary-color); }
.summary-grid { display: grid; grid-template-columns: repeat(4, 1fr); overflow: hidden; border: 1px solid var(--border-color); border-radius: 12px; background: var(--card-background); }
.summary-grid div { display: flex; flex-direction: column; padding: 1rem 1.1rem; border-left: 1px solid var(--border-color); }
.summary-grid div:first-child { border-left: 0; }
.summary-grid strong { font-size: 1.7rem; letter-spacing: -.03em; }
.summary-grid span { color: var(--text-color-secondary); font-size: var(--font-ui); }
.summary-grid .alert { background: #fff8e8; color: #84590e; }
.warnings { margin: .9rem 0; padding-left: 1.2rem; color: #87591d; }
.calendar-review-status { display: flex; align-items: center; gap: .7rem; margin: 1rem 0; padding: .75rem .85rem; border: 1px solid #e6c77a; border-radius: 9px; background: #fff8e8; color: #7d5717; }
.calendar-review-status.confirmed { border-color: #a9d8b6; background: #ebf8ef; color: #216a42; }
.calendar-review-status > i { font-size: 1.2rem; }
.calendar-review-status > div { display: grid; gap: .1rem; margin-right: auto; }
.calendar-review-status span { font-size: var(--font-supporting); }
.bulk-actions { display: flex; flex-wrap: wrap; align-items: center; gap: .55rem; margin-top: .9rem; padding: .7rem .8rem; border: 1px solid var(--border-color); border-radius: 9px; background: var(--surface-soft); }
.bulk-actions label { display: inline-flex; align-items: center; gap: .4rem; color: #344054; font-size: var(--font-ui); font-weight: 650; cursor: pointer; }
.bulk-actions label input { width: auto; min-height: auto; margin: 0; }
.bulk-actions > span { margin-right: auto; color: var(--text-color-secondary); font-size: var(--font-supporting); }
.table-wrap { overflow: auto; margin-top: 1rem; border: 1px solid var(--border-color); border-radius: 10px; }
table { width: 100%; border-collapse: collapse; font-size: var(--font-data); }
th, td { padding: .72rem .75rem; border-bottom: 1px solid #edf0f3; text-align: left; white-space: nowrap; }
th { background: var(--surface-soft); color: var(--text-color-secondary); font-size: var(--font-ui); font-weight: 700; }
tbody tr:last-child td { border-bottom: 0; }
tbody tr:hover { background: #fbfcfe; }
.preview-ranges { margin-top: 1rem; padding: .8rem 1rem; border-radius: 8px; background: var(--surface-soft); }
.preview-ranges ul { margin: .4rem 0 0; padding-left: 1.2rem; }
.resolution-choice { display: flex; gap: .35rem; }
.resolution-cell { display: flex; align-items: center; gap: .5rem; }
.resolution-choice label { display: inline-flex; align-items: center; gap: .3rem; padding: .42rem .55rem; border: 1px solid #d6dce5; border-radius: 7px; cursor: pointer; }
.resolution-choice label.selected { border-color: var(--primary-color); background: var(--highlight-bg); color: var(--primary-color-dark); }
.resolution-choice input { width: auto; min-height: 0; margin: 0; }
.status { display: inline-flex; align-items: center; padding: .24rem .52rem; border-radius: 999px; background: #fff4d6; color: #84590e; font-size: var(--font-supporting); white-space: nowrap; }
.status + .status { margin-left: .35rem; }
.status.error, .status.locked { background: #fdecea; color: #9b3b30; }
.status.available { background: #e4f5e9; color: #216a42; }
.status.current { background: var(--highlight-bg); color: var(--primary-color-dark); }
.notice { padding: .8rem 1rem; border-radius: 8px; border-left: 3px solid currentColor; }
.warning { background: #fff8e8; color: #8a5b16; }
.danger { background: #fdecea; color: #96382f; }
.success { background: #ebf8ef; color: #247147; }
.empty-row { text-align: center; color: var(--text-color-secondary); }

.versions-panel > .result-heading { flex-wrap: wrap; gap: .75rem; }
.versions-intro { margin: .35rem 0 0; font-size: var(--font-ui); }
.group-layout { display: grid; grid-template-columns: 12rem minmax(0, 1fr); gap: 1.2rem; margin-top: 1rem; border-top: 1px solid var(--border-color); }
.group-sidebar { padding: 1rem .8rem 1rem 0; border-right: 1px solid var(--border-color); }
.group-sidebar h4 { margin: 0 .65rem .6rem; color: var(--text-color-secondary); font-size: var(--font-supporting); }
.group-link { display: flex; align-items: center; gap: .55rem; width: 100%; min-height: 2.8rem; margin-bottom: .25rem; padding: .65rem; border: 1px solid transparent; border-radius: 8px; background: transparent; color: var(--text-color-primary); text-align: left; cursor: pointer; font: inherit; font-size: var(--font-ui); transition: background .15s, border-color .15s; }
.group-link:hover { background: var(--surface-soft); }
.group-link.selected { background: var(--highlight-bg); color: var(--primary-color-dark); font-weight: 700; }
.group-link.drop-target { border-color: var(--primary-color); background: var(--highlight-bg); box-shadow: inset 0 0 0 1px var(--primary-color); }
.group-link:focus-visible, .move-group-label select:focus-visible, .group-form input:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
.group-name { flex: 1; min-width: 0; overflow-wrap: anywhere; }
.group-count { flex-shrink: 0; min-width: 1.35rem; padding: .1rem .3rem; border-radius: 5px; background: var(--card-background); color: var(--text-color-secondary); font-size: var(--font-supporting); text-align: center; font-variant-numeric: tabular-nums; }
.group-unsaved { color: #996b13; }
.group-hint { margin: 1rem .65rem 0; color: var(--text-color-secondary); font-size: var(--font-supporting); line-height: 1.6; }
.group-content { min-width: 0; padding-top: 1rem; container-type: inline-size; }
.group-heading { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: .5rem; }
.group-heading h4 { margin: 0 0 .15rem; overflow-wrap: anywhere; font-size: var(--font-ui); }
.group-heading .muted { font-size: var(--font-supporting); }
.group-content .table-wrap { margin-top: .75rem; }
.versions-table { table-layout: fixed; font-size: var(--font-ui); }
.versions-table th, .versions-table td { padding: .95rem .85rem; white-space: normal; overflow-wrap: anywhere; vertical-align: middle; }
.versions-table th { padding-block: .75rem; font-weight: 600; }
.versions-table th:nth-child(1) { width: 30%; }
.versions-table th:nth-child(2) { width: 26%; }
.versions-table th:nth-child(3) { width: 23%; }
.versions-table th:nth-child(4) { width: 21%; }
.version-summary { transition: background .15s; }
.version-summary.version-expanded { background: #f1f7fa; }
.version-summary.version-expanded td { border-bottom-color: transparent; }
.version-summary.version-dirty .version-name-cell { box-shadow: inset 3px 0 #d3aa52; }
.version-identity { display: flex; align-items: center; gap: .55rem; }
.version-name { min-width: 0; }
.version-name > strong { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 650; line-height: 1.6; }
.version-meta { display: flex; flex-wrap: wrap; align-items: center; gap: .4rem; margin-top: .3rem; color: var(--text-color-secondary); font-size: var(--font-supporting); }
.version-meta .status { padding: .08rem .4rem; font-size: .8em; }
.draft-indicator { color: #946711; font-size: .85em; }
.version-date-summary, .version-stats { display: grid; gap: .3rem; font-variant-numeric: tabular-nums; }
.version-date-summary { font-size: var(--font-supporting); }
.version-date-summary > span { white-space: nowrap; }
.date-separator { padding: 0 .15rem; color: #8997a8; }
.version-stats small { color: var(--text-color-secondary); font-size: var(--font-supporting); }
.drag-handle { flex-shrink: 0; padding: .4rem .15rem; color: #8997a8; cursor: grab; font-size: 1.35rem; line-height: 1.2; }
.drag-handle:active { cursor: grabbing; }
.version-dragging { opacity: .5; }
.version-actions { display: flex; flex-wrap: wrap; align-items: center; gap: .4rem; }
.version-actions .p-button { flex-shrink: 0; min-height: 2.3rem; padding: .4rem .65rem; font-size: var(--font-supporting); }
.move-group-label { flex: 0 0 auto; min-width: 0; max-width: 100%; color: var(--primary-color-dark); font-size: var(--font-supporting); }
.move-group-label select { max-width: 100%; min-height: 2.3rem; padding: .35rem .15rem; border: 1px solid transparent; border-radius: 6px; background: transparent; color: inherit; font: inherit; cursor: pointer; }
.move-group-label select:hover { background: var(--highlight-bg); }
.versions-table .version-editor-row > td { padding: 0 .65rem .65rem; background: #f1f7fa; }
.version-editor { padding: 1.15rem; border: 1px solid #d9e5ec; border-radius: 9px; background: #f8fbfd; }
.editor-heading { display: flex; align-items: center; gap: .65rem; margin-bottom: 1rem; }
.version-editor h5 { margin: 0; font-size: var(--font-ui); font-weight: 650; }
.version-range-editor { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 1rem; }
.version-range-editor > label { display: grid; flex: 0 1 16rem; min-width: 0; gap: .4rem; color: var(--text-color-secondary); font-size: var(--font-supporting); }
.version-range-editor input { min-width: 0; font: inherit; }
.version-range-editor input:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
.version-range-editor :deep(.range-row) { padding: .65rem .8rem; }
.version-range-editor :deep(.range-inputs label) { flex: 0 1 16rem; }
.version-range-editor :deep(.range-inputs) { gap: .8rem; }
.range-validation { flex-basis: 100%; margin: 0; color: #96382f; font-size: var(--font-supporting); }
.version-specials { min-width: 0; margin: 1.2rem 0; padding: 0; border: 0; }
.version-specials legend { margin-bottom: .5rem; color: var(--text-color-secondary); font-size: var(--font-supporting); }
.version-specials > div { display: flex; flex-wrap: wrap; gap: .45rem; }
.version-specials label { display: inline-flex; align-items: center; gap: .35rem; padding: .4rem .6rem; border: 1px solid #d8e1e8; border-radius: 6px; background: #fff; cursor: pointer; font-size: var(--font-supporting); }
.version-specials label.selected { border-color: #aec6d4; background: #eaf3f8; color: var(--primary-color-dark); }
.version-specials input { margin: 0; }
.version-source-files h5 { color: var(--text-color-secondary); font-size: var(--font-supporting); font-weight: 500; }
.version-source-files > div { display: grid; grid-template-columns: 1fr 1fr; gap: .8rem 1.5rem; margin-top: .5rem; }
.version-source-files p { display: flex; align-items: flex-start; gap: .5rem; min-width: 0; margin: 0; font-size: var(--font-supporting); overflow-wrap: anywhere; }
.version-source-files i { margin-top: .3rem; color: #39805a; }
.version-source-files small { display: block; margin-bottom: .15rem; color: var(--text-color-secondary); font-size: .8em; }
.editor-hint { margin: 1rem 0 0; color: var(--text-color-secondary); font-size: var(--font-supporting); line-height: 1.6; }
.version-editor .notice { margin-top: .8rem; }
.version-editor-footer { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: .8rem; margin-top: 1rem; padding-top: .85rem; border-top: 1px solid #dce6ed; }
.version-delete, .version-save-actions { display: flex; flex-wrap: wrap; align-items: center; gap: .6rem; }
.version-delete small { display: flex; align-items: center; gap: .3rem; color: var(--text-color-secondary); font-size: var(--font-supporting); }
.version-save-actions { margin-left: auto; }
.version-editor .p-button { min-height: 2.4rem; padding: .5rem .8rem; font-size: var(--font-supporting); }
.group-dialog-heading { display: flex; align-items: center; gap: .85rem; min-width: 0; }
.group-dialog-icon { display: grid; place-items: center; flex: 0 0 2.85rem; height: 2.85rem; border: 1px solid #d9e5ec; border-radius: 12px; background: #edf4f8; color: var(--primary-color-dark); }
.group-dialog-icon i { font-size: 1.3rem; }
.group-dialog-heading h3 { margin: 0; color: var(--text-color-primary); font-size: 1.25rem; font-weight: 750; line-height: 1.4; }
.group-dialog-heading p { margin: .2rem 0 0; color: var(--text-color-secondary); font-size: var(--font-supporting); line-height: 1.5; }
.group-form { display: grid; gap: 1rem; }
.group-name-field { display: grid; gap: .55rem; }
.group-name-field label { color: var(--text-color-primary); font-size: var(--font-ui); font-weight: 650; }
.group-name-field input { min-width: 0; min-height: 3rem; padding: .75rem .9rem; font: inherit; font-size: var(--font-data); border-radius: 10px; }
.group-name-field input::placeholder { color: #8a96a6; }
.group-name-field input:focus-visible { outline: 3px solid #dce8ef; outline-offset: 1px; border-color: var(--primary-color); }
.group-form p { margin: 0; font-size: var(--font-supporting); line-height: 1.6; }
.group-form-hint { display: flex; align-items: flex-start; gap: .5rem; color: var(--text-color-secondary); }
.group-form-hint i { flex-shrink: 0; margin-top: .2rem; color: #7590a3; }
.group-form-actions { display: flex; justify-content: flex-end; gap: .65rem; margin: .5rem -1.75rem -1.5rem; padding: 1rem 1.75rem; border-top: 1px solid #e8edf2; background: #f8fafc; }
.group-form-actions .p-button { min-height: 2.65rem; padding: .65rem 1.1rem; border-radius: 8px; }

@container (max-width: 48rem) {
  .versions-table, .versions-table tbody { display: block; }
  .versions-table thead { display: none; }
  .versions-table tr { display: grid; grid-template-columns: 1fr 1fr; gap: .7rem 1rem; padding: .85rem; border-bottom: 1px solid var(--border-color); }
  .versions-table td { display: block; min-width: 0; padding: 0; border: 0; }
  .versions-table td[data-label]::before { content: attr(data-label); display: block; margin-bottom: .25rem; color: var(--text-color-secondary); font-size: var(--font-supporting); }
  .versions-table .version-name-cell, .versions-table .version-action-cell, .versions-table .empty-row, .versions-table .version-editor-row > td { grid-column: 1 / -1; }
  .versions-table .version-editor-row { padding: 0; }
  .version-editor { padding: .85rem; }
  .version-date-summary > span { white-space: normal; }
  .version-range-editor > label, .version-range-editor :deep(.range-inputs label) { flex: 1 1 10rem; }
  .version-source-files > div { grid-template-columns: 1fr; }
}

@media (max-width: 700px) {
  .group-layout { grid-template-columns: minmax(0, 1fr); gap: 0; }
  .group-sidebar { display: grid; grid-template-columns: 1fr 1fr; align-content: start; gap: .25rem; max-height: 15rem; overflow-y: auto; padding: .75rem 0; border-right: 0; border-bottom: 1px solid var(--border-color); }
  .group-sidebar h4, .group-hint { grid-column: 1 / -1; }
  .group-hint { margin-top: .35rem; }
  .group-link { height: auto; margin: 0; }
}

@media (max-width: 1000px) {
  .import-steps { grid-template-columns: 1fr; }
  .import-steps::before { display: none; }
  .step-card { height: auto; }
}

@media (max-width: 600px) {
  .page-heading, .result-heading { flex-direction: column; }
  .revision { padding-top: 0; }
  .import-panel { padding: 1rem; }
  .schedule-type-options { grid-template-columns: 1fr; }
  .upload-row { grid-template-columns: 3rem minmax(0, 1fr); }
  .upload-action { grid-column: 1 / -1; text-align: center; }
  .import-footer { align-items: stretch; flex-direction: column; }
  .import-footer .p-button { width: 100%; }
  .summary-grid { grid-template-columns: 1fr 1fr; }
  .summary-grid div:nth-child(3) { border-top: 1px solid var(--border-color); border-left: 0; }
  .summary-grid div:nth-child(4) { border-top: 1px solid var(--border-color); }
  .result-actions { width: 100%; }
  .result-actions .p-button { flex: 1; }
  .calendar-review-status { align-items: flex-start; flex-wrap: wrap; }
  .calendar-review-status > div { width: calc(100% - 2rem); }
  .calendar-review-status .p-button { width: 100%; }
  .versions-table tr { grid-template-columns: 1fr; }
  .version-range-editor :deep(.range-inputs label) { flex-basis: auto; }
}
</style>

<style>
.timetable-group-dialog.p-dialog { width: min(30rem, calc(100vw - 2rem)) !important; max-width: calc(100vw - 2rem) !important; height: auto !important; max-height: calc(100dvh - 2rem) !important; margin: 1rem !important; overflow: hidden; border: 1px solid #dbe3eb; border-radius: 18px !important; box-shadow: 0 24px 80px #142e4933; }
.timetable-group-dialog .p-dialog-header { align-items: flex-start; gap: .75rem; padding: 1.6rem 1.75rem 1.4rem; }
.timetable-group-dialog .p-dialog-header-icons { flex-shrink: 0; }
.timetable-group-dialog .p-dialog-header-close { width: 2rem; height: 2rem; border-radius: 8px; color: #8090a2; }
.timetable-group-dialog .p-dialog-header-close:hover { background: #eef3f7; color: #253f54; }
.timetable-group-dialog .p-dialog-content { padding: 0 1.75rem 1.5rem; }
</style>
