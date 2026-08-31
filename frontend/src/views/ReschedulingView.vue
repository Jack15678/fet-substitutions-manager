<template>
  <section class="rescheduling-page">
    <header v-show="!workflowPanelVisible" class="page-heading">
      <div>
        <h2>{{ $t('rescheduling.title') }}</h2>
      </div>
      <div class="page-actions">
        <span class="revision">{{ $t('rescheduling.revision', { revision: timetable.revision ?? '-' }) }}</span>
        <Button v-if="can('manual_arrangement.manage')" :label="$t('rescheduling.manualArrangement')" severity="secondary" outlined @click="openManualPanel()" />
        <Button v-if="can('absence.create')" :label="$t('rescheduling.addAbsence')" @click="openAbsencePanel" />
      </div>
    </header>

    <section v-show="!workflowPanelVisible" class="panel recommendations-panel">
      <div class="panel-title">
        <div><h3>{{ $t('rescheduling.steps.recommendations') }}</h3></div>
        <div v-if="analysis" class="analysis-actions">
          <small>{{ $t('rescheduling.counts', { resolved: analysis.resolved_count, unresolved: analysis.unresolved_count }) }}</small>
          <Button v-if="can('absence.create') && currentAbsenceIds.length" :label="$t('rescheduling.cancelAbsence')" severity="danger" text size="small" @click="cancelAbsence" />
        </div>
      </div>
      <p v-if="analysisError" class="entry-error" role="alert">{{ analysisError }}</p>
      <TransitionGroup v-if="batchAnalyses.length > 1" name="motion-list" tag="div" class="analysis-dates" role="tablist" :aria-label="$t('rescheduling.analysisDates')">
        <button
          v-for="item in batchAnalyses"
          :key="item.date"
          type="button"
          role="tab"
          :aria-selected="selectedAnalysisDate === item.date"
          :class="{ active: selectedAnalysisDate === item.date }"
          :disabled="analysisSwitchLoading"
          @click="selectAnalysisDate(item.date)"
        >{{ dateLabel(item.date) }}</button>
      </TransitionGroup>
      <div v-if="!analysis" class="empty-state">
        <p>{{ $t('rescheduling.analysisEmpty') }}</p>
        <Button v-if="can('absence.create')" :label="$t('rescheduling.addAbsence')" outlined @click="openAbsencePanel" />
      </div>
      <div v-else-if="!analysis.tasks.length" class="notice success">{{ $t('rescheduling.noTasks') }}</div>
      <TransitionGroup v-else name="motion-list" tag="div" class="task-list">
      <article v-for="task in analysis.tasks" :key="task.task_key" class="task-card">
        <div class="task-heading">
          <div><strong>{{ $t('records.period', { period: task.target.period }) }} · {{ task.target.class_code }} {{ task.target.subject }}</strong><small>{{ $t('rescheduling.originalTeacher', { teachers: joinItems(task.target.teacher_names) }) }}</small></div>
          <span :class="['status', task.status]">{{ task.status === 'recommended' ? $t('rescheduling.recommendable') : $t('rescheduling.unresolved') }}</span>
        </div>
        <template v-if="task.alternatives.length">
          <label>{{ $t('rescheduling.candidates') }}
            <select v-model="selectedCandidates[task.task_key]">
              <option v-for="candidate in task.alternatives" :key="candidate.id" :value="candidate.id">
                {{ optionLabel(candidate) }}{{ candidate.special_cross_day_moves ? ` · ${$t('rescheduling.specialCourseLater')}` : '' }}
              </option>
            </select>
          </label>
          <div class="movement-list" v-for="candidate in selectedForTask(task)" :key="candidate.id">
            <div v-for="(leg, index) in candidate.legs" :key="index">
              <span>{{ leg.class_code }} {{ leg.subject }}（{{ joinItems(leg.teacher_names) }}）</span>
              <b>{{ leg.from_date }} {{ $t('records.period', { period: leg.from_period }) }} → {{ leg.to_date }} {{ $t('records.period', { period: leg.to_period }) }}</b>
            </div>
            <small v-if="candidate.breaks_consecutive_lessons" class="candidate-warning">{{ $t('rescheduling.breaksConsecutiveLesson') }}</small>
          </div>
          <div class="candidate-actions">
            <Button :label="$t('rescheduling.verifyTimetables')" severity="secondary" outlined :loading="verificationLoading" @click="verifyTask(task)" />
            <Button v-if="can('manual_arrangement.manage')" :label="$t('rescheduling.useManualInstead')" severity="secondary" outlined @click="openManualPanel(task.task_key)" />
            <Button v-if="can('adjustment.confirm')" :label="$t('rescheduling.confirmArrangement')" severity="success" :loading="busy === task.task_key" @click="confirmTask(task)" />
          </div>
        </template>
        <div v-else class="unresolved-actions">
          <p class="unresolved-copy">{{ $t(task.blocking_reason === 'started' ? 'rescheduling.startedLesson' : 'rescheduling.noCandidate') }}</p>
          <Button v-if="can('manual_arrangement.manage')" :label="$t('rescheduling.arrangeThisLesson')" severity="secondary" outlined @click="openManualPanel(task.task_key)" />
        </div>
      </article>
      </TransitionGroup>
    </section>

    <Transition name="motion-fade">
    <section v-if="can('manual_arrangement.manage') && manualPanelVisible" class="manual-workspace">
      <header class="manual-heading">
        <div>
          <Button icon="pi pi-arrow-left" :aria-label="$t('common.back')" text rounded @click="manualPanelVisible = false" />
          <div><span>{{ $t('rescheduling.manualEyebrow') }}</span><h2>{{ $t('rescheduling.manualArrangement') }}</h2></div>
        </div>
        <small>{{ $t('rescheduling.manualQueueCount', { count: manualTasks.length }) }}</small>
      </header>

      <div v-if="manualLoading" class="manual-state">{{ $t('common.loading') }}</div>
      <div v-else-if="manualError" class="manual-state error">{{ manualError }}</div>
      <div v-else-if="!manualTasks.length" class="manual-state success">
        <strong>{{ $t('rescheduling.manualEmptyTitle') }}</strong>
        <span>{{ $t('rescheduling.manualEmptyHint') }}</span>
        <Button :label="$t('common.back')" outlined @click="manualPanelVisible = false" />
      </div>
      <template v-else>
        <section class="manual-queue" :aria-label="$t('rescheduling.manualQueue')">
          <header><strong>{{ $t('rescheduling.manualQueue') }}</strong><span>{{ $t('rescheduling.manualQueueHint') }}</span></header>
          <TransitionGroup name="motion-list" tag="div" class="manual-queue-scroll">
            <button
              v-for="task in manualTasks"
              :key="task.task_key"
              type="button"
              :class="['manual-queue-card', { active: task.task_key === selectedManualTaskKey }]"
              @click="selectManualTask(task.task_key)"
            >
              <span>{{ dateLabel(task.target.date) }} · {{ $t('records.period', { period: task.target.period }) }}</span>
              <strong>{{ task.target.class_code }} · {{ task.target.subject }}</strong>
              <small>{{ task.absent_teacher_name }}</small>
              <span :class="['status', task.status]">{{ task.status === 'recommended' ? $t('rescheduling.recommendable') : $t('rescheduling.unresolved') }}</span>
            </button>
          </TransitionGroup>
        </section>

        <div v-if="selectedManualTask" class="manual-layout">
          <section class="candidate-area">
            <header class="candidate-area-heading">
              <div><span>{{ $t('rescheduling.manualStep', { step: 1 }) }}</span><h3>{{ $t('rescheduling.chooseCoverTeacher') }}</h3></div>
              <small>{{ $t('rescheduling.candidateRule') }}</small>
            </header>
            <div v-if="selectedManualTask.co_teachers?.length" class="co-teacher-option">
              <div>
                <strong>{{ $t('rescheduling.coTeacherAvailableTitle', { teachers: coTeacherNames(selectedManualTask) }) }}</strong>
                <span>{{ $t('rescheduling.coTeacherAvailableHint') }}</span>
              </div>
              <Button
                :label="$t('rescheduling.confirmCoTeacherOnly')"
                severity="secondary"
                outlined
                :loading="busy === 'manual-co-teacher'"
                @click="confirmManualArrangement(true)"
              />
            </div>
            <div v-if="!selectedManualTask.candidates.length" class="manual-state compact error">
              {{ $t('rescheduling.noManualCandidate') }}
            </div>
            <TransitionGroup v-else name="motion-list" tag="div" class="teacher-card-grid">
              <button
                v-for="candidate in selectedManualTask.candidates"
                :key="candidate.id"
                type="button"
                :class="['teacher-card', { selected: candidate.id === selectedManualTeacherId }]"
                @click="selectedManualTeacherId = candidate.id"
              >
                <div class="teacher-card-heading">
                  <div><strong>{{ candidate.name }}</strong><span>{{ $t('rescheduling.coverCount', { count: candidate.cover_count }) }}</span></div>
                  <i aria-hidden="true"></i>
                </div>
                <div class="candidate-badges">
                  <span v-if="candidate.same_subject" class="same-subject">{{ $t('rescheduling.sameSubject') }}</span>
                  <span>{{ adjacentLabel(candidate) }}</span>
                </div>
                <div class="teacher-schedule">
                  <div v-for="slot in candidate.slots" :key="slot.period" :class="['teacher-slot', slot.state, { adjacent: isAdjacentSlot(slot.period) }]">
                    <b>{{ slot.period }}</b>
                    <span v-if="slot.state === 'target'">{{ $t('rescheduling.availableToCover') }}</span>
                    <span v-else-if="slot.lessons.length">{{ slot.lessons[0].class_code }}<small>{{ slot.lessons[0].subject }}</small></span>
                    <span v-else-if="slot.state === 'busy'">{{ $t('rescheduling.unavailable') }}</span>
                    <span v-else>{{ $t('rescheduling.freePeriod') }}</span>
                  </div>
                </div>
              </button>
            </TransitionGroup>
          </section>

          <aside class="manual-summary">
            <div class="summary-step"><span>{{ $t('rescheduling.manualStep', { step: 2 }) }}</span><h3>{{ $t('rescheduling.confirmManualArrangement') }}</h3></div>
            <dl>
              <div><dt>{{ $t('rescheduling.lessonToHandle') }}</dt><dd>{{ dateLabel(selectedManualTask.target.date) }} · {{ $t('records.period', { period: selectedManualTask.target.period }) }}</dd></div>
              <div><dt>{{ $t('rescheduling.classSubject') }}</dt><dd>{{ selectedManualTask.target.class_code }} · {{ selectedManualTask.target.subject }}</dd></div>
              <div><dt>{{ $t('rescheduling.absentTeacher') }}</dt><dd>{{ selectedManualTask.absent_teacher_name }}</dd></div>
              <div v-if="selectedManualTask.co_teachers?.length"><dt>{{ $t('rescheduling.remainingCoTeacher') }}</dt><dd>{{ coTeacherNames(selectedManualTask) }}</dd></div>
              <div><dt>{{ $t('rescheduling.coverTeacher') }}</dt><dd :class="{ pending: !selectedManualCandidate }">{{ selectedManualCandidate?.name || $t('rescheduling.notSelected') }}</dd></div>
            </dl>
            <p>{{ $t('rescheduling.manualConfirmHint') }}</p>
            <Button
              :label="$t('rescheduling.confirmManualCover')"
              severity="success"
              :loading="busy === 'manual-confirm'"
              :disabled="!selectedManualCandidate"
              @click="confirmManualArrangement()"
            />
          </aside>
        </div>
      </template>
    </section>
    </Transition>

    <Transition name="motion-fade">
    <form v-if="can('absence.create') && absencePanelVisible" class="absence-editor" @submit.prevent="createAndAnalyze">
      <aside class="absence-master">
        <header>
          <h3>{{ $t('rescheduling.currentAbsences') }}</h3>
          <small>{{ $t('rescheduling.absenceLimit', { count: absenceEntries.length }) }}</small>
        </header>
        <TransitionGroup name="motion-list" tag="div" class="absence-master-list" :aria-label="$t('rescheduling.currentAbsences')">
          <button
            v-for="entry in absenceEntries"
            :key="entry.id"
            type="button"
            :aria-pressed="activeAbsenceEntryId === entry.id"
            :class="['absence-master-item', { active: activeAbsenceEntryId === entry.id }]"
            @click="activeAbsenceEntryId = entry.id"
          >
            <strong>{{ entryTeacherName(entry) || $t('rescheduling.newAbsenceRecord') }}</strong>
            <span>{{ entry.data }}</span>
            <small>{{ entryPeriodSummary(entry) }}</small>
          </button>
        </TransitionGroup>
        <div class="absence-master-actions">
          <Button type="button" :label="$t('rescheduling.addAnotherTeacher')" outlined :disabled="absenceEntries.length >= 3" @click="addAbsenceEntry" />
          <span>{{ absenceEntries.length }}／3</span>
        </div>
      </aside>

      <section class="absence-detail">
        <header class="absence-detail-heading">
          <div>
            <h3>{{ $t('rescheduling.addAbsence') }}</h3>
            <p>{{ $t('rescheduling.addAbsenceHint') }}</p>
          </div>
          <Button
            v-if="absenceEntries.length > 1"
            type="button"
            :label="$t('rescheduling.removeAbsenceRecord')"
            severity="danger"
            text
            @click="removeAbsenceEntry(activeAbsenceEntry.id)"
          />
        </header>

        <Transition name="motion-fade" mode="out-in">
        <div v-if="activeAbsenceEntry" :key="activeAbsenceEntry.id" class="absence-detail-body">
          <div class="absence-entry-grid">
            <label>{{ $t('rescheduling.teacher') }}
              <select v-model.number="activeAbsenceEntry.professor_id" :disabled="activeAbsenceEntry.loading || !activeAbsenceEntry.active" required @change="onAbsenceTeacherChange(activeAbsenceEntry)">
                <option :value="null">{{ activeAbsenceEntry.loading ? $t('rescheduling.checkingDate') : activeAbsenceEntry.active ? $t('rescheduling.selectTeacher') : $t('rescheduling.invalidDate') }}</option>
                <option v-for="teacher in activeAbsenceEntry.teachers" :key="teacher.id" :value="teacher.id">{{ teacher.name }}</option>
              </select>
            </label>
            <label>{{ $t('rescheduling.absenceDate') }}
              <input v-model="activeAbsenceEntry.data" type="date" required @change="loadAbsenceEntryContext(activeAbsenceEntry)" />
            </label>
            <label>
              <span>{{ $t('rescheduling.absenceReason') }} <span class="required-marker" aria-hidden="true">*</span></span>
              <select
                :id="`absence-reason-${activeAbsenceEntry.id}`"
                v-model="activeAbsenceEntry.reason_type"
                :class="{ 'field-invalid': reasonErrorEntryId === activeAbsenceEntry.id }"
                :aria-invalid="reasonErrorEntryId === activeAbsenceEntry.id"
                :aria-describedby="reasonErrorEntryId === activeAbsenceEntry.id ? `absence-reason-error-${activeAbsenceEntry.id}` : undefined"
                :disabled="Boolean(activeAbsenceEntry.existing_case_id && activeAbsenceEntry.existing_reason_type)"
                required
                @change="clearReasonError(activeAbsenceEntry)"
                @invalid.prevent="showReasonError(activeAbsenceEntry, $event.target)"
              >
                <option value="">{{ $t('rescheduling.selectAbsenceReason') }}</option>
                <option v-for="reason in absenceReasonTypes" :key="reason" :value="reason">{{ $t(`rescheduling.absenceReasons.${reason}`) }}</option>
              </select>
              <small v-if="reasonErrorEntryId === activeAbsenceEntry.id" :id="`absence-reason-error-${activeAbsenceEntry.id}`" class="field-error" role="alert">{{ $t('rescheduling.absenceReasonRequired') }}</small>
            </label>
            <label v-if="activeAbsenceEntry.reason_type === 'other'">{{ $t('rescheduling.absenceReasons.other') }}
              <input v-model="activeAbsenceEntry.reason_detail" type="text" maxlength="200" :placeholder="$t('rescheduling.otherReasonPlaceholder')" :disabled="Boolean(activeAbsenceEntry.existing_case_id && activeAbsenceEntry.existing_reason_type)" />
            </label>
          </div>
          <p v-if="!activeAbsenceEntry.loading && activeAbsenceEntry.data && !activeAbsenceEntry.active" class="entry-error">{{ $t('rescheduling.invalidDate') }}</p>
          <p v-if="activeAbsenceEntry.existing_case_id" class="existing-absence-notice">
            {{ $t('rescheduling.existingAbsenceNotice', { periods: existingPeriodSummary(activeAbsenceEntry) }) }}
          </p>
          <div class="period-field">
            <div class="period-heading">
              <span>{{ $t('rescheduling.absentPeriods') }}</span>
              <label class="all-day"><input type="checkbox" :checked="entryAllDay(activeAbsenceEntry)" :disabled="activeAbsenceEntry.existing_periods.length === 9" @change="setEntryAllDay(activeAbsenceEntry, $event.target.checked)" />{{ $t('rescheduling.allDay') }}</label>
            </div>
            <div class="periods">
              <label v-for="period in 9" :key="period" :class="{ selected: activeAbsenceEntry.periods.includes(period), existing: activeAbsenceEntry.existing_periods.includes(period) }">
                <input v-model="activeAbsenceEntry.periods" type="checkbox" :value="period" :disabled="activeAbsenceEntry.existing_periods.includes(period)" />
                <span>{{ $t('records.period', { period }) }}<small v-if="activeAbsenceEntry.existing_periods.includes(period)">{{ $t('rescheduling.existingPeriod') }}</small></span>
              </label>
            </div>
          </div>
        </div>
        </Transition>

        <p v-if="absenceError" class="absence-form-error" role="alert">{{ absenceError }}</p>
        <footer class="absence-form-actions">
          <Button :label="$t('common.cancel')" outlined type="button" @click="absencePanelVisible = false" />
          <Button type="submit" :label="$t('rescheduling.createAndAnalyze')" class="progress-fill-button" :class="{ 'is-progressing': busy === 'analyze' }" :loading="busy === 'analyze'" :disabled="!canAttemptAnalyze" />
        </footer>
      </section>
    </form>
    </Transition>

    <Dialog v-model:visible="verificationVisible" modal :header="$t('rescheduling.verifyTitle')" :style="{ width: 'min(96vw, 1120px)' }" class="verification-dialog">
      <div v-if="verificationLoading" class="verification-loading">{{ $t('common.loading') }}</div>
      <div v-else class="verification-content">
        <p>{{ $t('rescheduling.verifyHint') }}</p>
        <section v-for="(teacher, teacherIndex) in verificationTimetables" :key="teacher.id" :class="['verification-teacher', `teacher-color-${teacherIndex + 1}`]">
          <h4>{{ teacher.name }}</h4>
          <div class="verification-wrap">
            <table class="verification-timetable">
              <thead><tr><th>{{ $t('rescheduling.date') }}</th><th v-for="period in 9" :key="period">{{ $t('records.period', { period }) }}</th></tr></thead>
              <tbody>
                <tr v-for="day in teacher.days" :key="day.date">
                  <th>{{ dateLabel(day.date) }}</th>
                  <td v-for="slot in day.slots" :key="slot.period">
                    <div v-if="slot.changed" class="verification-change">
                      <div><small>{{ $t('rescheduling.originalArrangement') }}</small><span>{{ arrangementLabel(slot.before) }}</span></div>
                      <div><small>{{ $t('rescheduling.newArrangement') }}</small><span>{{ arrangementLabel(slot.after) }}</span></div>
                    </div>
                    <template v-else>
                      <div v-for="lesson in slot.after" :key="lesson.key" class="verification-lesson">
                        <strong>{{ lesson.class_code }}</strong><span>{{ lesson.subject }}</span>
                      </div>
                    </template>
                    <span v-if="!slot.changed && !slot.after.length" class="slot-empty">—</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </Dialog>

    <section v-show="!workflowPanelVisible" class="panel effective-panel">
      <div class="panel-title">
        <div>
          <div class="title-copy"><h3>{{ $t('rescheduling.steps.effective') }}</h3><small>{{ $t('rescheduling.affectedHint') }}</small></div>
        </div>
        <div class="effective-filters">
          <label class="inline-date">{{ $t('rescheduling.date') }}<input v-model="effectiveDate" type="date" @change="loadEffective" /></label>
        </div>
      </div>
      <div>
        <div v-if="!affectedGroups.length" class="affected-empty">{{ $t('rescheduling.noAdjustments') }}</div>
        <template v-else>
          <div class="affected-view-bar">
            <div class="view-switch" role="group" :aria-label="$t('rescheduling.viewMode')">
              <button type="button" :class="{ active: affectedView === 'timetable' }" @click="affectedView = 'timetable'">{{ $t('rescheduling.timetableView') }}</button>
              <button type="button" :class="{ active: affectedView === 'cards' }" @click="affectedView = 'cards'">{{ $t('rescheduling.cardView') }}</button>
            </div>
            <div v-if="affectedView === 'timetable'" class="timetable-legend">
              <span><i class="moved-out"></i>{{ $t('rescheduling.movedOut') }}</span>
              <span><i class="moved-in"></i>{{ $t('rescheduling.movedIn') }}</span>
              <span><i class="covered"></i>{{ $t('rescheduling.covered') }}</span>
            </div>
          </div>
        <TransitionGroup v-if="affectedView === 'cards'" name="motion-list" tag="div" class="affected-grid">
          <article v-for="group in affectedGroups" :key="group.id" class="affected-card">
            <header>
              <div class="affected-card-title">
                <strong>{{ joinItems(group.classes) }}</strong>
                <span>{{ $t('rescheduling.affectedLessons', { count: group.legs.length }) }}</span>
                <span class="source-tag changed">{{ sourceLabel(group.source) }}</span>
              </div>
              <div v-if="!isCoverKind(group.source)" class="cycle-route" :aria-label="$t('rescheduling.cycleClosed', { number: 1 })">
                <template v-for="(_, index) in group.legs" :key="`route-${group.id}-${index}`">
                  <span class="cycle-route-step">{{ index + 1 }}</span><span class="cycle-route-arrow" aria-hidden="true">→</span>
                </template>
                <span class="cycle-route-step">1</span>
              </div>
            </header>
            <div v-if="isCoverKind(group.source)" class="cover-link">
              <div><small>{{ $t('rescheduling.coverAt') }}</small><b>{{ group.legs[0].from_date }} · {{ periodLabel(group.legs[0].from_period) }}</b></div>
              <span aria-hidden="true">→</span>
              <div><strong>{{ group.legs[0].class_code }} · {{ group.legs[0].subject }}</strong><span>{{ joinItems(adjustmentTeacherNames(group.source, group.legs[0])) }}</span></div>
            </div>
            <div v-else class="cycle-table-wrap">
              <table class="cycle-table" :aria-label="$t('rescheduling.cardView')">
                <thead><tr>
                  <th class="cycle-order">#</th>
                  <th>{{ $t('rescheduling.class') }} · {{ $t('rescheduling.subject') }}</th>
                  <th>{{ $t('rescheduling.teacherColumn') }}</th>
                  <th>{{ $t('rescheduling.originalSlot') }}</th>
                  <th class="cycle-table-arrow" aria-hidden="true"></th>
                  <th>{{ $t('rescheduling.currentSlot') }}</th>
                </tr></thead>
                <tbody>
                  <tr v-for="(leg, index) in group.legs" :key="`${group.id}-${index}`">
                    <td class="cycle-order"><span>{{ index + 1 }}</span></td>
                    <td><strong>{{ leg.class_code }} · {{ leg.subject }}</strong></td>
                    <td class="cycle-teacher">{{ joinItems(leg.teacher_names) }}</td>
                    <td class="cycle-time">{{ leg.from_date }} · {{ periodLabel(leg.from_period) }}</td>
                    <td class="cycle-table-arrow" aria-hidden="true">→</td>
                    <td class="cycle-time">{{ leg.to_date }} · {{ periodLabel(leg.to_period) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </article>
        </TransitionGroup>
          <div v-else class="mini-timetable-wrap">
            <table class="mini-timetable">
              <thead><tr><th>{{ $t('rescheduling.class') }}</th><th v-for="period in 9" :key="period">{{ $t('records.period', { period }) }}</th></tr></thead>
              <tbody>
                <tr v-for="row in classTimetables" :key="row.classCode">
                  <th>{{ row.classCode }}</th>
                  <td v-for="slot in row.periods" :key="slot.period" :class="{ affected: slot.outgoing.length || slot.incoming.length }">
                    <div v-for="lesson in slot.outgoing" :key="`out-${lesson.occurrence_id}`" class="slot-change moved-out">
                      <small>{{ $t('rescheduling.movedOut') }}</small><strong>{{ lesson.subject }}</strong><span>{{ joinItems(lesson.teacher_names) }}</span>
                    </div>
                    <div v-for="lesson in slot.incoming" :key="`in-${lesson.occurrence_id}`" :class="['slot-change', isCoverKind(lesson.source) ? 'covered' : 'moved-in']">
                      <small>{{ $t(isCoverKind(lesson.source) ? 'rescheduling.covered' : 'rescheduling.movedIn') }}</small><strong>{{ lesson.subject }}</strong><span>{{ joinItems(lesson.teacher_names) }}</span>
                    </div>
                    <div v-if="!slot.outgoing.length && !slot.incoming.length && slot.current.length" class="slot-current">
                      <template v-for="lesson in slot.current" :key="lesson.occurrence_id"><strong>{{ lesson.subject }}</strong><span>{{ joinItems(lesson.teacher_names) }}</span></template>
                    </div>
                    <span v-if="!slot.outgoing.length && !slot.incoming.length && !slot.current.length" class="slot-empty">—</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
      </div>
    </section>

    <section v-if="isAdmin" v-show="!workflowPanelVisible" class="panel leave-panel">
      <div class="leave-heading">
        <div><h3>{{ $t('leave.title') }}</h3><p>{{ $t('leave.description') }}</p></div>
        <Button v-if="editingLeaveId" :label="$t('leave.cancelEdit')" text @click="resetLeave" />
      </div>
      <form class="leave-form" @submit.prevent="saveLeave">
        <label>{{ $t('leave.teacher') }}
          <select v-model.number="leave.professor_id" required>
            <option :value="null">{{ $t('common.selectOption') }}</option>
            <option v-for="teacher in leaveTeachers" :key="teacher.id" :value="teacher.id">{{ teacher.name }}</option>
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
        <Button type="submit" :label="editingLeaveId ? $t('leave.update') : $t('leave.add')" :loading="leaveBusy" />
      </form>
      <TransitionGroup v-if="leaves.length" name="motion-list" tag="div" class="leave-list">
        <article v-for="item in leaves" :key="item.id">
          <div><strong>{{ item.teacher_name }}</strong><span>{{ leaveTypeLabel(item.leave_type) }} · {{ item.start_date }} → {{ item.end_date }}</span></div>
          <div><Button :label="$t('common.edit')" text @click="editLeave(item)" /><Button :label="$t('common.delete')" severity="danger" text @click="removeLeave(item.id)" /></div>
        </article>
      </TransitionGroup>
      <p v-else class="empty-state compact">{{ $t('leave.empty') }}</p>
    </section>

  </section>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import axios from 'axios'
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import { candidateOptionLabel } from './rescheduling/candidateLabel.js'

const props = defineProps({ dataGlobal: Date, isAdmin: Boolean, can: { type: Function, required: true } })
const { t, locale } = useI18n()
const joinItems = (items) => items.join(locale.value === 'en' ? ', ' : '、')
const iso = (value) => {
  const d = value || new Date()
  const local = new Date(d.getTime() - d.getTimezoneOffset() * 60000)
  return local.toISOString().slice(0, 10)
}

const busy = ref('')
const dateContextLoading = ref(false)
const timetable = ref({ active: false })
let absenceEntryId = 0
const absenceReasonTypes = ['sick', 'follow_up', 'team_training', 'other']
const newAbsenceEntry = () => ({
  id: ++absenceEntryId,
  professor_id: null,
  data: iso(props.dataGlobal),
  periods: [],
  existing_case_id: null,
  existing_periods: [],
  existing_reason_type: '',
  absences: [],
  reason_type: '',
  reason_detail: '',
  teachers: [],
  active: false,
  loading: false,
})
const absencePanelVisible = ref(false)
const manualPanelVisible = ref(false)
const manualLoading = ref(false)
const manualError = ref('')
const manualRevision = ref(0)
const manualTasks = ref([])
const selectedManualTaskKey = ref('')
const selectedManualTeacherId = ref(null)
const absenceEntries = ref([])
const activeAbsenceEntryId = ref(null)
const reasonErrorEntryId = ref(null)
const absenceError = ref('')
const analysisError = ref('')
const currentAbsenceIds = ref([])
const analysis = ref(null)
const batchAnalyses = ref([])
const selectedAnalysisDate = ref('')
const analysisSwitchLoading = ref(false)
const selectedCandidates = reactive({})
const effectiveDate = ref(iso(props.dataGlobal))
const effective = ref({ lessons: [] })
const affectedView = ref('timetable')
const verificationVisible = ref(false)
const verificationLoading = ref(false)
const verificationTimetables = ref([])
const leaves = ref([])
const leaveTeachers = ref([])
const leaveBusy = ref(false)
const editingLeaveId = ref(null)
const leave = reactive({ professor_id: null, leave_type: 'sick', start_date: '', end_date: '' })

const workflowPanelVisible = computed(() => (
  (absencePanelVisible.value && props.can('absence.create'))
  || (manualPanelVisible.value && props.can('manual_arrangement.manage'))
))
const selectedManualTask = computed(() => manualTasks.value.find(task => task.task_key === selectedManualTaskKey.value))
const selectedManualCandidate = computed(() => selectedManualTask.value?.candidates.find(candidate => candidate.id === selectedManualTeacherId.value))
const coTeacherNames = (task) => joinItems((task?.co_teachers || []).map(teacher => teacher.name))
const isCoverKind = (kind) => ['emergency_cover', 'co_teacher_solo'].includes(kind)
const adjustmentTeacherNames = (source, leg) => {
  if (source === 'emergency_cover' && leg.replacement_teacher_name) return [leg.replacement_teacher_name]
  if (source === 'co_teacher_solo') {
    return leg.teacher_names.filter((_, index) => Number(leg.teacher_ids[index]) !== Number(leg.replaced_teacher_id))
  }
  return leg.teacher_names
}
const canAttemptAnalyze = computed(() => absenceEntries.value.length > 0 && absenceEntries.value.every(entry => (
  !entry.loading && entry.active && entry.professor_id && entry.data
  && entry.periods.some(period => !entry.existing_periods.includes(period))
)))
const canAnalyze = computed(() => canAttemptAnalyze.value && absenceEntries.value.every(entry => absenceReasonTypes.includes(entry.reason_type)))
const activeAbsenceEntry = computed(() => absenceEntries.value.find(entry => entry.id === activeAbsenceEntryId.value))
const affectedGroups = computed(() => (effective.value.adjustments || []).map(adjustment => ({
  id: adjustment.id,
  source: adjustment.kind,
  classes: [...new Set(adjustment.legs.map(leg => leg.class_code))],
  legs: adjustment.legs
})))
const affectedLessons = computed(() => affectedGroups.value.flatMap(group => group.legs
  .filter(leg => leg.from_date === effectiveDate.value || leg.to_date === effectiveDate.value)
  .map((leg, index) => ({
    ...leg,
    occurrence_id: `adjustment-${group.id}-${index}`,
    source: group.source,
    teacher_names: adjustmentTeacherNames(group.source, leg),
    displayFromPeriod: leg.from_period,
    displayToPeriod: leg.to_period,
    displayFromDate: leg.from_date,
    displayToDate: leg.to_date
  }))))
const classTimetables = computed(() => [...new Set(affectedLessons.value.map(lesson => lesson.class_code))].sort().map(classCode => ({
  classCode,
  periods: Array.from({ length: 9 }, (_, index) => {
    const period = index + 1
    return {
      period,
      current: (effective.value.lessons || []).filter(lesson => lesson.lesson_id && lesson.class_code === classCode && lesson.period === period),
      outgoing: affectedLessons.value.filter(lesson => lesson.class_code === classCode && lesson.displayFromDate === effectiveDate.value && lesson.displayFromPeriod === period && (lesson.displayFromPeriod !== lesson.displayToPeriod || lesson.displayFromDate !== lesson.displayToDate)),
      incoming: affectedLessons.value.filter(lesson => lesson.class_code === classCode && lesson.displayToDate === effectiveDate.value && lesson.displayToPeriod === period)
    }
  })
})))
const periodLabel = (period) => period ? t('records.period', { period }) : '—'
watch(() => props.dataGlobal, (value) => {
  const nextDate = iso(value)
  effectiveDate.value = nextDate
  loadDateContext()
  loadEffective()
})

const loadDateContext = async () => {
  const requestedDate = iso(props.dataGlobal)
  if (!requestedDate) {
    timetable.value = { active: false }
    return
  }
  dateContextLoading.value = true
  timetable.value = { active: false }
  try {
    const timetableResponse = await axios.get('/api/timetables/current', { params: { data: requestedDate } })
    if (iso(props.dataGlobal) !== requestedDate) return
    timetable.value = timetableResponse.data
  } finally {
    if (iso(props.dataGlobal) === requestedDate) dateContextLoading.value = false
  }
}

const loadAbsenceEntryContext = async (entry) => {
  const requestedDate = entry.data
  entry.loading = true
  entry.active = false
  entry.teachers = []
  entry.absences = []
  entry.periods = []
  entry.existing_case_id = null
  entry.existing_periods = []
  entry.existing_reason_type = ''
  entry.reason_type = ''
  entry.reason_detail = ''
  try {
    const [timetableResponse, teacherResponse, absenceResponse] = await Promise.all([
      axios.get('/api/timetables/current', { params: { data: requestedDate }, _silent: true }),
      axios.get('/api/rescheduling/teachers', { params: { data: requestedDate }, _silent: true }),
      axios.get('/api/absence-cases', { params: { data: requestedDate }, _silent: true }),
    ])
    if (entry.data !== requestedDate) return
    entry.active = Boolean(timetableResponse.data.active)
    entry.teachers = teacherResponse.data
    entry.absences = absenceResponse.data
    if (!entry.teachers.some(teacher => teacher.id === entry.professor_id)) entry.professor_id = null
    applyExistingAbsence(entry)
  } catch (error) {
    if (entry.data === requestedDate) entry.professor_id = null
  } finally {
    if (entry.data === requestedDate) entry.loading = false
  }
}

const applyExistingAbsence = (entry) => {
  const existing = entry.absences.find(item => (
    item.status !== 'cancelled' && Number(item.professor_id) === Number(entry.professor_id)
  ))
  entry.existing_case_id = existing?.id || null
  entry.existing_periods = (existing?.periods || []).map(Number).sort((a, b) => a - b)
  entry.existing_reason_type = existing?.reason_type || ''
  entry.periods = [...entry.existing_periods]
  entry.reason_type = existing?.reason_type || ''
  entry.reason_detail = existing?.reason_detail || ''
}

const onAbsenceTeacherChange = (entry) => {
  entry.periods = []
  entry.reason_type = ''
  entry.reason_detail = ''
  applyExistingAbsence(entry)
}

const openAbsencePanel = () => {
  manualPanelVisible.value = false
  absenceError.value = ''
  reasonErrorEntryId.value = null
  absenceEntries.value = [newAbsenceEntry()]
  activeAbsenceEntryId.value = absenceEntries.value[0].id
  absencePanelVisible.value = true
  loadAbsenceEntryContext(absenceEntries.value[0])
}

const selectManualTask = (taskKey) => {
  selectedManualTaskKey.value = taskKey
  selectedManualTeacherId.value = manualTasks.value.find(task => task.task_key === taskKey)?.candidates[0]?.id || null
}

const loadManualArrangements = async (preferredTaskKey = '') => {
  manualLoading.value = true
  manualError.value = ''
  try {
    const response = (await axios.get('/api/manual-arrangements', { _silent: true })).data
    manualRevision.value = response.revision
    manualTasks.value = response.tasks || []
    const nextKey = [preferredTaskKey, selectedManualTaskKey.value]
      .find(key => manualTasks.value.some(task => task.task_key === key)) || manualTasks.value[0]?.task_key || ''
    if (nextKey) selectManualTask(nextKey)
    else {
      selectedManualTaskKey.value = ''
      selectedManualTeacherId.value = null
    }
  } catch (error) {
    manualTasks.value = []
    manualError.value = error.response?.data?.detail || t('app.errors.unexpected')
  } finally { manualLoading.value = false }
}

const openManualPanel = async (taskKey = '') => {
  absencePanelVisible.value = false
  manualPanelVisible.value = true
  await loadManualArrangements(taskKey)
}

const isAdjacentSlot = (period) => {
  const targetPeriod = selectedManualTask.value?.target.period
  return targetPeriod && Math.abs(Number(period) - Number(targetPeriod)) === 1
}

const adjacentLabel = (candidate) => {
  if (!candidate.adjacent_total || candidate.adjacent_busy_count === 0) return t('rescheduling.adjacentAllFree')
  if (candidate.adjacent_busy_count === candidate.adjacent_total) return t('rescheduling.adjacentAllBusy')
  return t('rescheduling.adjacentPartlyFree')
}

const confirmManualArrangement = async (coTeacherOnly = false) => {
  const task = selectedManualTask.value
  const candidate = selectedManualCandidate.value
  if (!task || (!coTeacherOnly && !candidate)) return
  busy.value = coTeacherOnly ? 'manual-co-teacher' : 'manual-confirm'
  manualError.value = ''
  const handledDate = task.target.date
  try {
    await axios.post('/api/manual-arrangements/cover', {
      absence_case_id: task.absence_case_id,
      occurrence_id: task.target.occurrence_id,
      replacement_teacher_id: coTeacherOnly ? null : candidate.id,
      co_teacher_only: coTeacherOnly,
      expected_revision: manualRevision.value,
    }, { _silent: true })
    await loadManualArrangements()
    if (analysis.value && selectedAnalysisDate.value === handledDate) await selectAnalysisDate(handledDate)
    await Promise.all([loadDateContext(), loadEffective()])
  } catch (error) {
    manualError.value = error.response?.data?.detail || t('app.errors.unexpected')
  } finally { busy.value = '' }
}

const addAbsenceEntry = () => {
  if (absenceEntries.value.length >= 3) return
  const entry = newAbsenceEntry()
  absenceEntries.value.push(entry)
  activeAbsenceEntryId.value = entry.id
  loadAbsenceEntryContext(entry)
}

const removeAbsenceEntry = (id) => {
  absenceEntries.value = absenceEntries.value.filter(entry => entry.id !== id)
  if (reasonErrorEntryId.value === id) reasonErrorEntryId.value = null
  if (!absenceEntries.value.some(entry => entry.id === activeAbsenceEntryId.value)) {
    activeAbsenceEntryId.value = absenceEntries.value[0]?.id || null
  }
}
const entryAllDay = (entry) => entry.periods.length === 9
const setEntryAllDay = (entry, checked) => {
  entry.periods = checked ? Array.from({ length: 9 }, (_, index) => index + 1) : [...entry.existing_periods]
}
const entryTeacherName = (entry) => entry.teachers.find(teacher => teacher.id === entry.professor_id)?.name
const entryPeriodSummary = (entry) => entry.periods.length
  ? joinItems([...entry.periods].sort((a, b) => a - b).map(period => t('records.period', { period })))
  : t('rescheduling.noPeriodsSelected')
const existingPeriodSummary = (entry) => joinItems(entry.existing_periods.map(period => t('records.period', { period })))
const clearReasonError = (entry) => {
  if (reasonErrorEntryId.value === entry.id && absenceReasonTypes.includes(entry.reason_type)) reasonErrorEntryId.value = null
}
const showReasonError = (entry, field) => {
  reasonErrorEntryId.value = entry.id
  field?.focus()
}
const focusMissingReason = async () => {
  const entry = absenceEntries.value.find(item => !absenceReasonTypes.includes(item.reason_type))
  if (!entry) return false
  activeAbsenceEntryId.value = entry.id
  reasonErrorEntryId.value = entry.id
  await nextTick()
  document.getElementById(`absence-reason-${entry.id}`)?.focus()
  return true
}

const applyDefaults = () => {
  for (const key of Object.keys(selectedCandidates)) delete selectedCandidates[key]
  for (const task of analysis.value?.tasks || []) {
    selectedCandidates[task.task_key] = task.recommended?.id || task.alternatives[0]?.id
  }
}

const clearStaleAnalysis = async () => {
  currentAbsenceIds.value = []
  analysis.value = null
  batchAnalyses.value = []
  selectedAnalysisDate.value = ''
  for (const key of Object.keys(selectedCandidates)) delete selectedCandidates[key]
  analysisError.value = ''
  await Promise.all([loadDateContext(), loadEffective()])
}

const recoverStaleAbsence = async (error) => {
  if (error.response?.status !== 404) return false
  await clearStaleAnalysis()
  return true
}

const createAndAnalyze = async () => {
  if (await focusMissingReason() || !canAnalyze.value) return
  busy.value = 'analyze'
  absenceError.value = ''
  try {
    const created = (await axios.post('/api/absence-cases/batch', {
      items: absenceEntries.value.map(entry => ({
        professor_id: entry.professor_id,
        data: entry.data,
        periods: entry.periods.map(Number),
        reason_type: entry.reason_type,
        reason_detail: entry.reason_type === 'other' ? entry.reason_detail.trim() || null : null,
      })),
    }, { _silent: true })).data
    currentAbsenceIds.value = created.batch_absence_case_ids
    batchAnalyses.value = created.analyses || [{ ...created, date: absenceEntries.value[0].data }]
    const globalDate = iso(props.dataGlobal)
    const firstDate = batchAnalyses.value.some(item => item.date === globalDate) ? globalDate : batchAnalyses.value[0].date
    await selectAnalysisDate(firstDate, false)
    absencePanelVisible.value = false
    absenceEntries.value = []
    activeAbsenceEntryId.value = null
  } catch (error) {
    absenceError.value = error.response?.data?.detail || t('app.errors.unexpected')
  } finally { busy.value = '' }
}

const selectAnalysisDate = async (targetDate, refresh = true) => {
  let selected = batchAnalyses.value.find(item => item.date === targetDate)
  if (!selected) return
  selectedAnalysisDate.value = targetDate
  if (refresh && selected.absence_case_ids?.length) {
    analysisError.value = ''
    analysisSwitchLoading.value = true
    try {
      const latest = (await axios.post(`/api/absence-cases/${selected.absence_case_ids[0]}/analyze`, null, { _silent: true })).data
      selected = { date: targetDate, ...latest }
      batchAnalyses.value = batchAnalyses.value.map(item => item.date === targetDate ? selected : item)
    } catch (error) {
      if (!await recoverStaleAbsence(error)) analysisError.value = error.response?.data?.detail || t('app.errors.unexpected')
      return
    } finally { analysisSwitchLoading.value = false }
  }
  analysis.value = selected
  applyDefaults()
}

const selectedForTask = (task) => task.alternatives.filter(item => item.id === selectedCandidates[task.task_key])
const dateLabel = (value) => new Intl.DateTimeFormat(locale.value === 'en' ? 'en-HK' : 'zh-HK', {
  month: 'numeric', day: 'numeric', weekday: 'short'
}).format(new Date(`${value}T12:00:00`))
const optionDateLabel = (value) => {
  const day = new Date(`${value}T12:00:00`)
  return locale.value === 'en'
    ? new Intl.DateTimeFormat('en-HK', { month: 'numeric', day: 'numeric', weekday: 'short' }).format(day)
    : `${day.getMonth() + 1}/${day.getDate()}（${'日一二三四五六'[day.getDay()]}）`
}
const optionLabel = (candidate) => candidateOptionLabel(candidate, {
  date: optionDateLabel, period: periodLabel, join: joinItems, kind: kindLabel,
})
const arrangementLabel = (lessons) => lessons.length
  ? joinItems([...new Set(lessons.map(lesson => `${lesson.class_code} ${lesson.subject}`))])
  : t('rescheduling.freePeriod')
const legTeacherIds = (leg) => (leg.teachers || leg.teacher_ids || []).map(Number)
const verifyTask = async (task) => {
  const candidate = selectedForTask(task)[0]
  if (!candidate) return
  verificationVisible.value = true
  verificationLoading.value = true
  verificationTimetables.value = []
  try {
    const dates = [...new Set(candidate.legs.flatMap(leg => [leg.from_date, leg.to_date]))].sort()
    const responses = await Promise.all(dates.map(async day => [
      day, (await axios.get('/api/effective-timetable', { params: { data: day } })).data.lessons || []
    ]))
    const lessonsByDate = Object.fromEntries(responses)
    const teacherNames = new Map()
    for (const leg of candidate.legs) {
      legTeacherIds(leg).forEach((id, index) => teacherNames.set(id, leg.teacher_names[index] || String(id)))
      if (leg.replacement_teacher_id) teacherNames.set(Number(leg.replacement_teacher_id), leg.replacement_teacher_name || String(leg.replacement_teacher_id))
    }
    verificationTimetables.value = [...teacherNames.entries()].map(([teacherId, name]) => ({
      id: teacherId,
      name,
      days: dates.map(day => ({
        date: day,
        slots: Array.from({ length: 9 }, (_, index) => {
          const period = index + 1
          const before = lessonsByDate[day]
            .filter(lesson => Number(lesson.period) === period && lesson.teacher_ids.map(Number).includes(teacherId))
            .map(lesson => ({ ...lesson, key: lesson.occurrence_id }))
          const removals = candidate.legs.filter(leg => leg.from_date === day && Number(leg.from_period) === period
            && (candidate.kind === 'emergency_cover'
              ? Number(leg.replaced_teacher_id) === teacherId
              : legTeacherIds(leg).includes(teacherId)))
          const additions = candidate.legs.filter(leg => leg.to_date === day && Number(leg.to_period) === period
            && (candidate.kind === 'emergency_cover'
              ? Number(leg.replacement_teacher_id) === teacherId
              : legTeacherIds(leg).includes(teacherId)))
          const removedOccurrenceIds = new Set(removals.map(leg => leg.occurrence_id))
          const after = before
            .filter(lesson => !removedOccurrenceIds.has(lesson.occurrence_id))
            .concat(additions.map((leg, legIndex) => ({ ...leg, key: `${candidate.id}-${legIndex}-${teacherId}` })))
          return { period, before, after, changed: Boolean(removals.length || additions.length) }
        })
      }))
    }))
  } finally {
    verificationLoading.value = false
  }
}
const confirmTask = async (task) => {
  const candidateId = selectedCandidates[task.task_key]
  if (!candidateId) return
  busy.value = task.task_key
  analysisError.value = ''
  try {
    const response = (await axios.post('/api/adjustments/confirm', {
      absence_case_id: task.absence_case_id, candidate_id: candidateId, expected_revision: analysis.value.revision
    }, { _silent: true })).data
    analysis.value = response.analysis
    batchAnalyses.value = batchAnalyses.value.map(item => item.date === selectedAnalysisDate.value
      ? { date: selectedAnalysisDate.value, ...response.analysis }
      : item)
    applyDefaults(); await loadDateContext(); await loadEffective()
  } catch (error) {
    if (!await recoverStaleAbsence(error)) analysisError.value = error.response?.data?.detail || t('app.errors.unexpected')
  } finally { busy.value = '' }
}

const loadEffective = async () => {
  if (!effectiveDate.value) return
  effective.value = (await axios.get('/api/effective-timetable', { params: { data: effectiveDate.value } })).data
}

const cancelAbsence = async () => {
  if (!currentAbsenceIds.value.length) return
  analysisError.value = ''
  try {
    await axios.post('/api/absence-cases/cancel-batch', { absence_case_ids: currentAbsenceIds.value }, { _silent: true })
    await clearStaleAnalysis()
  } catch (error) {
    if (!await recoverStaleAbsence(error)) analysisError.value = error.response?.data?.detail || t('app.errors.unexpected')
  }
}

const kindLabel = (kind) => t(`records.kinds.${kind}`, kind)
const sourceLabel = (source) => t(`rescheduling.sources.${source}`, source)
const leaveTypeLabel = (value) => t(`leave.types.${value}`, value)

const loadLeaves = async () => {
  const [leaveResponse, teacherResponse] = await Promise.all([
    axios.get('/api/teacher-leaves'), axios.get('/api/rescheduling/teachers')
  ])
  leaves.value = leaveResponse.data
  leaveTeachers.value = teacherResponse.data
}
const resetLeave = () => {
  editingLeaveId.value = null
  Object.assign(leave, { professor_id: null, leave_type: 'sick', start_date: '', end_date: '' })
}
const editLeave = (item) => {
  editingLeaveId.value = item.id
  Object.assign(leave, { professor_id: item.professor_id, leave_type: item.leave_type, start_date: item.start_date, end_date: item.end_date })
}
const saveLeave = async () => {
  leaveBusy.value = true
  try {
    const url = editingLeaveId.value ? `/api/teacher-leaves/${editingLeaveId.value}` : '/api/teacher-leaves'
    await axios[editingLeaveId.value ? 'put' : 'post'](url, leave)
    resetLeave()
    await Promise.all([loadLeaves(), loadDateContext(), loadEffective()])
  } finally { leaveBusy.value = false }
}
const removeLeave = async (id) => {
  await axios.delete(`/api/teacher-leaves/${id}`)
  if (editingLeaveId.value === id) resetLeave()
  await Promise.all([loadLeaves(), loadDateContext(), loadEffective()])
}

const resumeAbsence = async (record) => {
  absencePanelVisible.value = false
  manualPanelVisible.value = false
  busy.value = 'analyze'
  currentAbsenceIds.value = [record.entity_id]
  effectiveDate.value = record.date
  analysis.value = null
  try {
    timetable.value = (await axios.get('/api/timetables/current', { params: { data: record.date } })).data
    const result = (await axios.post(`/api/absence-cases/${record.entity_id}/analyze`)).data
    batchAnalyses.value = [{ date: record.date, ...result }]
    selectedAnalysisDate.value = record.date
    analysis.value = batchAnalyses.value[0]
    applyDefaults()
    await loadEffective()
  } finally { busy.value = '' }
}

defineExpose({ resumeAbsence })

onMounted(async () => {
  await Promise.all([loadDateContext(), loadEffective(), ...(props.isAdmin ? [loadLeaves()] : [])])
})
</script>

<style scoped>
.rescheduling-page { display: grid; gap: 1rem; color: var(--text-color-primary); }
.page-heading { display: flex; justify-content: space-between; gap: 2rem; align-items: center; padding: .15rem 0 .75rem; border-bottom: 1px solid var(--border-color); }
.page-heading h2 { margin: 0 0 .3rem; color: var(--primary-color-dark); font-size: clamp(1.55rem, 3vw, 1.95rem); line-height: 1.2; letter-spacing: -.025em; }
.page-heading p { max-width: 65ch; color: var(--text-color-secondary); }
.page-actions { display: flex; align-items: center; gap: 1rem; }
.revision { color: var(--text-color-secondary); font-size: var(--font-supporting); white-space: nowrap; }
.manual-workspace { display: grid; gap: 1rem; min-width: 0; }
.manual-heading { display: flex; align-items: center; justify-content: space-between; gap: 1rem; padding-bottom: .8rem; border-bottom: 1px solid var(--border-color); }
.manual-heading > div { display: flex; align-items: center; gap: .55rem; }
.manual-heading h2 { margin: .05rem 0 0; color: var(--primary-color-dark); font-size: clamp(1.45rem, 3vw, 1.85rem); letter-spacing: -.025em; }
.manual-heading span, .candidate-area-heading span, .summary-step span { color: #58708b; font-size: var(--font-supporting); font-weight: 750; letter-spacing: .05em; text-transform: uppercase; }
.manual-heading small { color: var(--text-color-secondary); }
.manual-state { display: grid; min-height: 230px; place-items: center; gap: .6rem; padding: 2rem; border: 1px solid var(--border-color); background: #fff; color: var(--text-color-secondary); text-align: center; }
.manual-state.success { background: #f4fbf6; color: #216a42; }
.manual-state.error { background: #fff8f6; color: #9b3b30; }
.manual-state.compact { min-height: 150px; }
.manual-queue { min-width: 0; padding: 1rem; border: 1px solid var(--border-color); background: #fff; }
.manual-queue > header { display: flex; align-items: baseline; gap: .65rem; margin-bottom: .75rem; }
.manual-queue > header span { color: var(--text-color-secondary); font-size: var(--font-supporting); }
.manual-queue-scroll { display: flex; gap: .6rem; overflow-x: auto; padding-bottom: .2rem; }
.manual-queue-card { display: flex; flex: 0 0 215px; flex-direction: column; gap: .25rem; padding: .8rem .85rem; border: 1px solid var(--border-color); border-left: 3px solid #9aa9b9; border-radius: 3px; background: #fff; color: var(--text-color-primary); text-align: left; cursor: pointer; }
.manual-queue-card:hover { border-color: #8aa0b8; background: #f9fbfc; }
.manual-queue-card.active { border-color: #315f8f; border-left-color: #315f8f; background: #f0f5fa; box-shadow: 0 0 0 1px #315f8f; }
.manual-queue-card span, .manual-queue-card small { color: var(--text-color-secondary); font-size: var(--font-supporting); }
.manual-queue-card strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.manual-queue-card .status { align-self: flex-start; margin-top: .2rem; }
.manual-layout { display: grid; grid-template-columns: minmax(0, 1fr) 295px; gap: 1rem; align-items: start; }
.candidate-area { min-width: 0; padding: 1rem; border: 1px solid var(--border-color); background: #fff; }
.candidate-area-heading { display: flex; align-items: end; justify-content: space-between; gap: 1rem; margin-bottom: .9rem; }
.candidate-area-heading h3, .summary-step h3 { margin: .12rem 0 0; color: var(--primary-color-dark); font-size: var(--font-critical); }
.candidate-area-heading small { max-width: 44ch; color: var(--text-color-secondary); font-size: var(--font-supporting); text-align: right; }
.co-teacher-option { display: flex; align-items: center; justify-content: space-between; gap: 1rem; margin-bottom: .85rem; padding: .8rem .85rem; border: 1px solid #a9c8b4; border-left: 3px solid #2f7d55; border-radius: 4px; background: #f2faf5; }
.co-teacher-option > div { display: flex; flex-direction: column; gap: .18rem; }
.co-teacher-option strong { color: #216a42; font-size: var(--font-data); }
.co-teacher-option span { color: var(--text-color-secondary); font-size: var(--font-supporting); }
.co-teacher-option .p-button { flex: 0 0 auto; }
.teacher-card-grid { position: relative; display: grid; grid-auto-columns: minmax(250px, 1fr); grid-auto-flow: column; gap: .75rem; overflow-x: auto; padding: 2px 2px .55rem; }
.teacher-card { min-width: 0; padding: 0; overflow: hidden; border: 1px solid var(--border-color); border-radius: var(--radius-md); background: #fff; color: var(--text-color-primary); text-align: left; cursor: pointer; transition: border-color var(--motion-fast) var(--motion-ease), box-shadow var(--motion-fast) var(--motion-ease), transform var(--motion-fast) var(--motion-ease); }
.teacher-card:hover { border-color: #7e97af; transform: translateY(-1px); }
.teacher-card.selected { border-color: #315f8f; box-shadow: 0 0 0 2px rgba(49, 95, 143, .16); }
.teacher-card-heading { display: flex; align-items: center; justify-content: space-between; gap: .5rem; padding: .8rem .85rem .55rem; }
.teacher-card-heading > div { display: flex; min-width: 0; flex-direction: column; gap: .1rem; }
.teacher-card-heading strong { overflow: hidden; color: var(--primary-color-dark); font-size: var(--font-critical); text-overflow: ellipsis; white-space: nowrap; }
.teacher-card-heading span { color: var(--text-color-secondary); font-size: var(--font-supporting); }
.teacher-card-heading i { width: .85rem; height: .85rem; flex: 0 0 auto; border: 2px solid #a6b2bf; border-radius: 50%; }
.teacher-card.selected .teacher-card-heading i { border: 3px solid #fff; background: #315f8f; box-shadow: 0 0 0 1px #315f8f; }
.candidate-badges { display: flex; flex-wrap: wrap; gap: .3rem; padding: 0 .85rem .65rem; }
.candidate-badges span { padding: .18rem .4rem; border-radius: 2px; background: #eef2f5; color: #536274; font-size: var(--font-supporting); font-weight: 700; }
.candidate-badges .same-subject { background: #e6f4ea; color: #216a42; }
.teacher-schedule { display: grid; border-top: 1px solid var(--border-color); }
.teacher-slot { display: grid; grid-template-columns: 2.25rem minmax(0, 1fr); min-height: 2.75rem; align-items: stretch; border-bottom: 1px solid #edf0f3; background: #fff; }
.teacher-slot:last-child { border-bottom: 0; }
.teacher-slot > b { display: grid; place-items: center; border-right: 1px solid #edf0f3; background: #f7f9fa; color: #596779; font-size: var(--font-supporting); font-variant-numeric: tabular-nums; }
.teacher-slot > span { display: flex; min-width: 0; align-items: center; justify-content: space-between; gap: .35rem; padding: .35rem .45rem; color: var(--text-color-secondary); font-size: var(--font-ui); }
.teacher-slot small { overflow: hidden; color: inherit; font-size: var(--font-supporting); text-overflow: ellipsis; white-space: nowrap; }
.teacher-slot.busy > span { color: #536274; }
.teacher-slot.adjacent { background: #fffaf0; }
.teacher-slot.adjacent > b { background: #fff4da; color: #805c12; }
.teacher-slot.target { background: #e7f5eb; }
.teacher-slot.target > b { background: #cfe9d8; color: #216a42; }
.teacher-slot.target > span { color: #216a42; font-weight: 750; }
.manual-summary { position: sticky; top: 1rem; display: grid; gap: 1rem; padding: 1rem; border: 1px solid #315f8f; border-top: 3px solid #315f8f; background: #fff; }
.manual-summary dl { display: grid; gap: 0; margin: 0; }
.manual-summary dl div { display: grid; gap: .16rem; padding: .65rem 0; border-bottom: 1px solid #edf0f3; }
.manual-summary dt { color: var(--text-color-secondary); font-size: var(--font-supporting); }
.manual-summary dd { margin: 0; color: var(--primary-color-dark); font-size: var(--font-data); font-weight: 700; }
.manual-summary dd.pending { color: #8b96a3; font-weight: 500; }
.manual-summary p { margin: 0; color: var(--text-color-secondary); font-size: var(--font-supporting); line-height: 1.5; }
.manual-summary .p-button { width: 100%; }
.panel { min-width: 0; background: var(--card-background); border: 1px solid var(--border-color); border-radius: var(--radius-lg); padding: 1.2rem; box-shadow: var(--shadow-panel); }
.panel-title { display: flex; align-items: center; justify-content: space-between; gap: 1rem; margin-bottom: 1rem; }
.panel-title > div { display: flex; align-items: center; gap: .65rem; }
.panel-title h3 { margin: 0; font-size: var(--font-data); }
.panel-title small { color: var(--text-color-secondary); }
.title-copy { display: flex; flex-direction: column; gap: .12rem; }
.analysis-actions { display: flex; align-items: center !important; gap: .45rem; }
.analysis-dates { display: flex; gap: 0; margin: -0.25rem 0 1rem; border-bottom: 1px solid var(--border-color); overflow-x: auto; }
.analysis-dates button { padding: .55rem .8rem; border: 0; border-bottom: 2px solid transparent; background: transparent; color: var(--text-color-secondary); cursor: pointer; font: inherit; font-size: var(--font-ui); font-weight: 650; white-space: nowrap; transition: color var(--motion-fast) var(--motion-ease), background-color var(--motion-fast) var(--motion-ease); }
.analysis-dates button:hover { color: var(--primary-color-dark); }
.analysis-dates button.active { border-bottom-color: var(--primary-color); color: var(--primary-color-dark); }
.analysis-dates button:focus-visible { box-shadow: var(--focus-ring); }
.analysis-dates button:disabled { cursor: wait; opacity: .6; }
.absence-editor { display: grid; grid-template-columns: 280px minmax(0, 1fr); min-height: calc(100dvh - 10rem); overflow: hidden; border: 1px solid var(--border-color); border-radius: var(--radius-lg); background: #fff; box-shadow: var(--shadow-panel); }
.absence-master { display: flex; min-width: 0; flex-direction: column; border-right: 1px solid var(--border-color); background: #f5f7f9; }
.absence-master > header { display: flex; align-items: baseline; justify-content: space-between; gap: .75rem; padding: 1.4rem 1.2rem 1rem; border-bottom: 1px solid var(--border-color); }
.absence-master h3 { margin: 0; color: var(--primary-color-dark); font-size: var(--font-data); }
.absence-master > header small, .absence-master-actions span { color: var(--text-color-secondary); font-size: var(--font-supporting); }
.absence-master-list { display: grid; }
.absence-master-item { display: flex; min-width: 0; flex-direction: column; gap: .28rem; padding: 1rem 1.15rem; border: 0; border-left: 3px solid transparent; border-bottom: 1px solid var(--border-color); background: transparent; color: var(--text-color-primary); text-align: left; cursor: pointer; transition: background-color .15s ease, border-color .15s ease; }
.absence-master-item:hover { background: #edf2f6; }
.absence-master-item.active { border-left-color: var(--primary-color-dark); background: #fff; }
.absence-master-item:focus-visible { position: relative; z-index: 1; box-shadow: inset var(--focus-ring); outline: none; }
.absence-master-item strong { color: var(--primary-color-dark); font-size: var(--font-critical); overflow-wrap: anywhere; }
.absence-master-item span { color: #42566a; font-size: var(--font-data); font-variant-numeric: tabular-nums; }
.absence-master-item small { color: var(--text-color-secondary); font-size: var(--font-supporting); overflow-wrap: anywhere; }
.absence-master-actions { display: grid; gap: .75rem; margin-top: auto; padding: 1.1rem; text-align: center; }
.absence-detail { display: flex; min-width: 0; flex-direction: column; background: #fff; }
.absence-detail-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 1.5rem; padding: 1.6rem 2rem 1.35rem; border-bottom: 1px solid var(--border-color); }
.absence-detail-heading h3 { margin: 0; color: var(--primary-color-dark); font-size: clamp(1.45rem, 2.4vw, 1.85rem); letter-spacing: -.025em; }
.absence-detail-heading p { max-width: 58ch; margin: .35rem 0 0; color: var(--text-color-secondary); font-size: var(--font-supporting); }
.absence-detail-body { display: grid; gap: 2rem; width: 100%; max-width: 960px; padding: 2rem; }
.absence-entry-grid { display: grid; grid-template-columns: 1.25fr 1fr; gap: .75rem; }
.absence-detail label { display: flex; flex-direction: column; gap: .4rem; color: #344054; font-size: var(--font-ui); font-weight: 650; }
.required-marker, .field-error { color: #9b3b30; }
.field-error { font-size: var(--font-ui); font-weight: 500; }
.absence-detail select.field-invalid { border-color: #b5473c; box-shadow: 0 0 0 2px rgba(181, 71, 60, .12); }
.entry-error, .absence-form-error { margin: .55rem 0 0; color: #9b3b30; font-size: var(--font-ui); }
.absence-form-error { padding: 0 2rem; }
.absence-form-actions { display: flex; justify-content: flex-end; gap: .65rem; margin-top: auto; padding: 1rem 2rem; border-top: 1px solid var(--border-color); background: #fbfcfd; }
select, input[type=date], input[type=file], input[type=text], textarea { width: 100%; min-height: 2.55rem; border: 1px solid #c8d2dd; border-radius: 4px; padding: .6rem .7rem; background: #fff; color: var(--text-color-primary); }
select:hover, input:hover, textarea:hover { border-color: #aeb8c5; }
select:focus, input:focus, textarea:focus { border-color: var(--primary-color); }
input[type=checkbox] { accent-color: var(--primary-color); }
input[type=file] { padding: .45rem; }
.period-heading { display: flex; align-items: center; justify-content: space-between; gap: .75rem; font-size: var(--font-ui); font-weight: 650; }
.absence-editor .all-day { flex-direction: row; align-items: center; gap: .4rem; font-weight: 600; cursor: pointer; }
.all-day input { width: auto; min-height: auto; }
.periods { display: grid; grid-template-columns: repeat(3, 1fr); gap: .7rem; margin-top: .65rem; }
.periods label { display: flex; min-height: 4.35rem; flex-direction: row; align-items: center; justify-content: center; border: 1px solid #cbd5df; border-radius: 3px; padding: .7rem !important; font-weight: 600 !important; cursor: pointer; transition: background-color .15s ease, border-color .15s ease, color .15s ease; }
.periods label:hover { border-color: #aeb8c5; background: var(--surface-soft); }
.periods label.selected { border-color: var(--primary-color-dark); background: var(--primary-color-dark); color: #fff; }
.periods label.existing { border-color: #b8c9d8; background: #eaf0f5; color: var(--primary-color-dark); cursor: not-allowed; }
.periods label span { display: flex; flex-direction: column; align-items: center; gap: .15rem; }
.periods label small { color: var(--text-color-secondary); font-size: .7em; }
.existing-absence-notice { margin: 0; padding: .75rem 1rem; border-left: 3px solid #6f91b1; background: #edf4fa; color: #36536d; }
.periods input { width: auto; min-height: auto; }
.notice { padding: .8rem 1rem; border-radius: 3px; border-left: 3px solid currentColor; }
.warning { background: #fff8e8; color: #8a5b16; }
.success { background: #ebf8ef; color: #247147; }
.empty-state { display: grid; place-items: center; min-height: 150px; padding: 2rem; border: 1px dashed var(--border-strong); border-radius: var(--radius-md); background: rgba(245, 247, 248, .72); color: var(--text-color-secondary); text-align: center; }
.empty-state p { margin: 0 0 .9rem; }
.task-list { position: relative; display: grid; gap: .8rem; }
.task-card { padding: 1rem; border: 1px solid var(--border-color); border-left: 3px solid #6f91b1; border-radius: var(--radius-md); background: #fff; }
.task-heading { display: flex; justify-content: space-between; gap: 1rem; margin-bottom: .8rem; }
.task-heading div { display: flex; flex-direction: column; gap: .2rem; }
.task-heading small { color: var(--text-color-secondary); }
.status, .source-tag { display: inline-flex; align-items: center; width: fit-content; padding: .24rem .52rem; border-radius: 3px; background: #eef1f4; color: #596476; font-size: var(--font-supporting); white-space: nowrap; }
.status.recommended, .status.confirmed, .source-tag.changed { background: #e4f5e9; color: #216a42; }
.status.unresolved { background: #fdecea; color: #9b3b30; }
.movement-list { margin: .7rem 0; padding: .7rem .8rem; border-radius: 3px; background: var(--surface-soft); }
.movement-list div { display: flex; justify-content: space-between; gap: 1rem; padding: .3rem 0; font-size: var(--font-data); }
.movement-list b { color: var(--primary-color-dark); text-align: right; }
.candidate-actions { display: flex; justify-content: flex-end; gap: .55rem; }
:global(.verification-dialog .p-dialog-header) { padding: 1.25rem 1.5rem; border-bottom: 1px solid var(--border-color); }
:global(.verification-dialog .p-dialog-content) { padding: 1.25rem 1.5rem 1.5rem; }
.verification-loading { display: grid; min-height: 180px; place-items: center; color: var(--text-color-secondary); }
.verification-content > p { margin: 0 0 1rem; color: var(--text-color-secondary); }
.verification-teacher { --teacher-accent: #315f8f; --teacher-border: #aac3de; --teacher-soft: #edf4fb; }
.verification-teacher.teacher-color-2 { --teacher-accent: #2f7d55; --teacher-border: #a9c8b4; --teacher-soft: #edf8f1; }
.verification-teacher.teacher-color-3 { --teacher-accent: #a05f16; --teacher-border: #e0bd8d; --teacher-soft: #fff5e8; }
.verification-teacher + .verification-teacher { margin-top: 1rem; }
.verification-teacher h4 { display: inline-flex; margin: 0 0 .45rem; border-left: 4px solid var(--teacher-accent); padding: .35rem .6rem; background: var(--teacher-soft); color: var(--teacher-accent); }
.verification-wrap { overflow-x: auto; border: 1px solid var(--border-color); border-top: 3px solid var(--teacher-accent); border-radius: 4px; }
.verification-timetable { min-width: 1320px; table-layout: fixed; font-size: var(--font-supporting); }
.verification-timetable th, .verification-timetable td { width: 134px; height: 82px; padding: .55rem; vertical-align: top; }
.verification-timetable th:first-child { width: 112px; }
.verification-lesson { display: flex; flex-direction: column; gap: .05rem; padding: .3rem; border-radius: 5px; color: #596476; }
.verification-lesson + .verification-lesson { margin-top: .2rem; }
.verification-lesson strong { font-size: var(--font-data); }
.verification-lesson span { font-size: var(--font-ui); line-height: 1.4; overflow-wrap: anywhere; }
.verification-change { display: grid; gap: .25rem; border: 1px solid var(--teacher-border); border-left: 3px solid var(--teacher-accent); border-radius: 4px; padding: .35rem; background: var(--teacher-soft); }
.verification-change > div { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: .3rem; align-items: baseline; }
.verification-change small { color: var(--teacher-accent); font-size: var(--font-supporting); font-weight: 800; }
.verification-change span { color: #344054; font-size: var(--font-critical); font-weight: 650; line-height: 1.4; overflow-wrap: anywhere; }
.unresolved-copy { margin: 0; color: #9b493d; }
.candidate-warning { display: block; margin-top: .4rem; color: #8a5b16; font-size: var(--font-supporting); }
.unresolved-actions { display: flex; align-items: center; justify-content: space-between; gap: 1rem; }
.effective-filters { display: flex; align-items: center; gap: 1rem; }
.effective-panel .inline-date { display: flex; align-items: center; gap: .55rem; color: var(--text-color-secondary); font-size: var(--font-ui); }
.effective-panel .inline-date input { width: auto; }
.affected-view-bar { display: flex; align-items: center; justify-content: space-between; gap: 1rem; margin-bottom: .75rem; }
.view-switch { display: inline-flex; padding: .2rem; border-radius: 4px; background: var(--surface-soft); }
.view-switch button { padding: .42rem .7rem; border: 0; border-radius: 3px; background: transparent; color: var(--text-color-secondary); cursor: pointer; font-size: var(--font-ui); font-weight: 650; transition: background .15s ease, color .15s ease; }
.view-switch button:hover { color: var(--text-color-primary); }
.view-switch button.active { background: #fff; color: var(--primary-color-dark); box-shadow: 0 1px 3px rgba(28, 45, 78, .12); }
.view-switch button:focus-visible { box-shadow: var(--focus-ring); }
.timetable-legend { display: flex; flex-wrap: wrap; gap: .8rem; color: var(--text-color-secondary); font-size: var(--font-supporting); }
.timetable-legend span { display: flex; align-items: center; gap: .3rem; }
.timetable-legend i { width: .65rem; height: .65rem; border-radius: 2px; }
.timetable-legend .moved-out { background: #fbe5e2; }
.timetable-legend .moved-in { background: #def1e5; }
.timetable-legend .covered { background: #fff0c7; }
.affected-grid { position: relative; display: grid; gap: .75rem; }
.affected-card { min-width: 0; padding: 1rem; border: 1px solid var(--border-color); border-left: 3px solid #6f91b1; border-radius: var(--radius-md); background: #fff; }
.affected-card header { display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; margin-bottom: .8rem; }
.affected-card-title { display: flex; flex-wrap: wrap; align-items: center; gap: .45rem .7rem; }
.affected-card header strong { font-size: var(--font-data); }
.affected-card-title > span:not(.source-tag) { color: var(--text-color-secondary); font-size: var(--font-supporting); }
.cycle-route { display: flex; align-items: center; gap: .3rem; color: #216a42; }
.cycle-route-step { display: grid; width: 1.75rem; height: 1.75rem; place-items: center; border: 1px solid #70a086; border-radius: 50%; font-size: var(--font-supporting); font-weight: 750; font-variant-numeric: tabular-nums; }
.cycle-route-arrow { color: #70a086; font-size: .85rem; }
.cycle-table-wrap { overflow-x: auto; border: 1px solid var(--border-color); border-radius: 4px; }
.cycle-table { min-width: 800px; font-size: var(--font-data); }
.cycle-table th, .cycle-table td { padding: .65rem .75rem; vertical-align: middle; }
.cycle-table th { background: #f8faf9; color: #596476; font-size: var(--font-supporting); }
.cycle-table td { color: var(--text-color-primary); }
.cycle-table tbody tr:hover { background: #fbfdfc; }
.cycle-table .cycle-order { width: 3rem; text-align: center; }
.cycle-order span { display: grid; width: 1.75rem; height: 1.75rem; margin: auto; place-items: center; border-radius: 50%; background: #2f7d55; color: #fff; font-size: var(--font-supporting); font-weight: 750; }
.cycle-table .cycle-table-arrow { width: 2rem; padding-inline: .2rem; color: #70a086; text-align: center; }
.cycle-table th.cycle-table-arrow { color: transparent; }
.cycle-table strong { white-space: nowrap; }
.cycle-teacher { color: var(--text-color-secondary) !important; white-space: nowrap; }
.cycle-time { font-variant-numeric: tabular-nums; white-space: nowrap; }
.cover-link { display: grid; grid-template-columns: minmax(170px, auto) auto minmax(220px, 1fr); align-items: center; gap: .75rem; padding: .8rem; border-radius: 4px; background: #fff8e5; }
.cover-link > div { display: flex; flex-direction: column; gap: .15rem; }
.cover-link small, .cover-link div span { color: var(--text-color-secondary); font-size: var(--font-supporting); }
.cover-link > span { color: #a57516; font-size: 1.2rem; font-weight: 800; }
.cover-link b { color: #805c12; font-size: var(--font-data); }
.affected-empty { display: grid; min-height: 110px; place-items: center; border-radius: 3px; background: var(--surface-soft); color: var(--text-color-secondary); text-align: center; }
.mini-timetable-wrap { overflow-x: auto; border: 1px solid var(--border-color); border-radius: 4px; }
.mini-timetable { min-width: 1360px; table-layout: fixed; font-size: var(--font-supporting); }
.mini-timetable th, .mini-timetable td { width: 138px; padding: .55rem; vertical-align: top; }
.mini-timetable thead th { text-align: center; }
.mini-timetable th:first-child { position: sticky; left: 0; z-index: 1; width: 92px; background: #fff; color: var(--text-color-primary); font-size: var(--font-data); }
.mini-timetable thead th:first-child { z-index: 2; background: var(--surface-soft); }
.mini-timetable td { height: 90px; background: #fff; }
.mini-timetable td.affected { background: #fbfcfe; }
.slot-change, .slot-current { display: flex; min-width: 0; flex-direction: column; gap: .05rem; padding: .3rem .38rem; border-radius: 5px; }
.slot-change + .slot-change { margin-top: .25rem; }
.slot-change small { font-size: var(--font-supporting); font-weight: 650; }
.slot-change strong, .slot-current strong { font-size: var(--font-data); overflow-wrap: anywhere; }
.slot-change span, .slot-current span { color: var(--text-color-secondary); font-size: var(--font-ui); overflow-wrap: anywhere; }
.slot-change.moved-out { background: #fbe5e2; color: #8e3f37; }
.slot-change.moved-in { background: #def1e5; color: #216a42; }
.slot-change.covered { background: #fff0c7; color: #805c12; }
.slot-current { color: #596476; }
.slot-empty { display: block; padding-top: .65rem; color: #b5bdc8; text-align: center; }
table { width: 100%; min-width: 720px; border-collapse: collapse; font-size: var(--font-data); }
th, td { padding: .72rem .75rem; border-bottom: 1px solid #edf0f3; text-align: left; }
th { background: var(--surface-soft); color: var(--text-color-secondary); font-size: var(--font-ui); font-weight: 700; white-space: nowrap; }
tbody tr:last-child td { border-bottom: 0; }
tbody tr:hover { background: #fbfcfe; }
.leave-heading, .leave-list article { display: flex; align-items: center; justify-content: space-between; gap: 1rem; }
.leave-heading { align-items: flex-start; }
.leave-heading h3 { margin: 0 0 .3rem; }
.leave-heading p, .leave-list span { color: var(--text-color-secondary); }
.leave-form { display: grid; grid-template-columns: 1.2fr 1fr .8fr .8fr auto; align-items: end; gap: .75rem; margin: 1rem 0; }
.leave-form label { display: flex; flex-direction: column; gap: .35rem; color: #344054; font-size: var(--font-ui); font-weight: 650; }
.leave-list article { padding: .75rem 0; border-top: 1px solid #edf0f3; }
.leave-list article > div:first-child { display: flex; flex-direction: column; gap: .2rem; }
.leave-list span { font-size: var(--font-data); }
.empty-state.compact { min-height: 80px; }
@media (max-width: 900px) {
  .manual-layout { grid-template-columns: 1fr; }
  .manual-summary { position: static; }
  .teacher-card-grid { grid-auto-columns: 240px; }
  .absence-editor { grid-template-columns: 220px minmax(0, 1fr); }
  .absence-detail-heading, .absence-detail-body { padding-inline: 1.25rem; }
  .absence-form-actions { padding-inline: 1.25rem; }
  .leave-form { grid-template-columns: 1fr 1fr; }
  .leave-form .p-button { grid-column: 1 / -1; }
  .movement-list div { flex-direction: column; gap: .2rem; }
  .movement-list b { text-align: left; }
}

@media (max-width: 600px) {
  :global(.verification-dialog .p-dialog-header), :global(.verification-dialog .p-dialog-content) { padding: 1rem; }
  .manual-heading { align-items: flex-start; }
  .manual-heading small { padding-top: .4rem; }
  .manual-queue { padding: .8rem; }
  .candidate-area { padding: .85rem; }
  .candidate-area-heading { align-items: flex-start; flex-direction: column; }
  .candidate-area-heading small { text-align: left; }
  .co-teacher-option { align-items: stretch; flex-direction: column; }
  .unresolved-actions { align-items: stretch; flex-direction: column; }
  .absence-editor { grid-template-columns: 1fr; grid-template-rows: auto minmax(0, 1fr); min-height: calc(100dvh - 9rem); }
  .absence-master { border-right: 0; border-bottom: 1px solid var(--border-color); }
  .absence-master > header { padding: .8rem .85rem .65rem; }
  .absence-master-list { display: flex; overflow-x: auto; }
  .absence-master-item { flex: 0 0 165px; padding: .75rem .85rem; border-left: 0; border-bottom: 3px solid transparent; border-right: 1px solid var(--border-color); }
  .absence-master-item.active { border-bottom-color: var(--primary-color-dark); }
  .absence-master-actions { display: flex; align-items: center; justify-content: space-between; margin-top: 0; padding: .7rem .85rem; text-align: left; }
  .absence-detail-heading { align-items: flex-start; flex-direction: column; gap: .4rem; padding: 1.15rem .85rem 1rem; }
  .absence-detail-heading h3 { font-size: 1.35rem; }
  .absence-detail-body { gap: 1.25rem; padding: 1.1rem .85rem 1.5rem; }
  .absence-form-error { padding-inline: .85rem; }
  .absence-form-actions { position: sticky; bottom: 0; padding: .8rem .85rem; }
  .periods { gap: .4rem; }
  .periods label { min-height: 3.25rem; padding: .45rem !important; font-size: var(--font-ui); }
  .page-heading { flex-direction: column; gap: .35rem; }
  .page-actions { width: 100%; flex-wrap: wrap; justify-content: space-between; }
  .page-actions .revision { width: 100%; }
  .panel-title { align-items: flex-start; }
  .effective-panel .panel-title { flex-direction: column; }
  .effective-filters { width: 100%; align-items: flex-start; flex-direction: column-reverse; }
  .affected-view-bar { align-items: flex-start; flex-direction: column; }
  .analysis-actions { align-items: flex-end !important; flex-direction: column; }
  .task-heading { flex-direction: column; }
  .candidate-actions { align-items: stretch; flex-direction: column; }
  .affected-card header { align-items: stretch; flex-direction: column; }
  .cycle-route { justify-content: flex-end; }
  .leave-heading, .leave-list article { align-items: flex-start; flex-direction: column; }
  .leave-form { grid-template-columns: 1fr; }
  .absence-entry-grid { grid-template-columns: 1fr; }
  .panel { padding: 1rem; }
}

:global(html[data-text-size="extra-large"] .recommendations-panel) { padding: .8rem; }
:global(html[data-text-size="extra-large"] .panel-title) { flex-wrap: wrap; margin-bottom: .65rem; }
:global(html[data-text-size="extra-large"] .panel-title h3),
:global(html[data-text-size="extra-large"] .task-heading strong) { font-size: var(--font-critical); }
:global(html[data-text-size="extra-large"] .task-card) { margin-bottom: .55rem; padding: .8rem; }
:global(html[data-text-size="extra-large"] .task-heading) { flex-wrap: wrap; margin-bottom: .55rem; }
:global(html[data-text-size="extra-large"] .task-heading .status) { padding: .35rem .55rem; font-size: var(--font-ui); }
:global(html[data-text-size="extra-large"] .task-card > label) { display: grid; gap: .3rem; font-size: var(--font-ui); font-weight: 650; }
:global(html[data-text-size="extra-large"] .movement-list) { margin: .5rem 0; padding: .5rem .65rem; }
:global(html[data-text-size="extra-large"] .movement-list div) { display: grid; grid-template-columns: minmax(10rem, .8fr) minmax(17rem, 1.2fr); gap: .75rem; padding: .25rem 0; }
:global(html[data-text-size="extra-large"] .movement-list b) { text-align: left; }
:global(html[data-text-size="extra-large"] .candidate-actions) { flex-wrap: wrap; gap: .4rem; }
:global(html[data-text-size="extra-large"] .view-switch button),
:global(html[data-text-size="extra-large"] .analysis-dates button) { min-height: 3rem; padding: .55rem .85rem; }

@media (max-width: 900px) {
  :global(html[data-text-size="extra-large"] .movement-list div) { grid-template-columns: 1fr; gap: .1rem; }
}
</style>
