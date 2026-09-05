"""API for timetable import, absence analysis and confirmed lesson swaps."""
from datetime import date
from io import BytesIO
import json
import math
import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from auth_utils import require_admin, require_any_permission, require_permission
from calendar_import import parse_calendar_docx
from dependencies import get_db
from models import (
    AbsenceCase,
    Configuracio,
    Professor,
    ProfessorBaixa,
    ScheduleAdjustment,
    ScheduleAdjustmentLeg,
    ScheduleAudit,
    SchoolClosure,
    TimetableGroup,
    TimetableImportPreview,
    TimetableLesson,
    TimetableTeacherSlot,
    TimetableVersion,
)
from daily_exports import (
    build_daily_pdf,
    build_daily_xlsx,
    daily_export_data,
    get_period_times,
    save_period_times,
)
from rescheduling_service import (
    MAX_CYCLE_LESSONS_KEY,
    adjacent_teaching_count,
    analyze_absences,
    apply_import_resolutions,
    build_import_preview,
    bump_schedule_revision,
    candidate_from_analysis,
    effective_occurrences,
    get_max_cycle_lessons,
    get_schedule_revision,
    is_post_exam_version,
    normalize_subject,
    validate_move_legs,
    absence_keys,
    professor_ids_for_version,
    schedule_slot_started,
    version_for_date,
    version_ranges,
    serialize_ranges,
    matching_range_start,
)
from time_utils import hong_kong_now, hong_kong_today, utc_iso, utc_now
from permissions import user_has_permission


router = APIRouter(tags=["調課推薦"])
MAX_UPLOAD_BYTES = 12 * 1024 * 1024


class CalendarClosureInput(BaseModel):
    date: date
    note: Optional[str] = Field(default=None, max_length=500)


class TimetableGroupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)

    @model_validator(mode="after")
    def validate_name(self):
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("請填寫分組名稱")
        return self


class MoveTimetableGroupRequest(BaseModel):
    group_id: Optional[int] = Field(..., gt=0)


class TimetableDateRange(BaseModel):
    effective_from: date
    effective_to: date


class ActivateTimetableRequest(BaseModel):
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    effective_ranges: Optional[list[TimetableDateRange]] = Field(default=None, min_length=1)
    resolutions: dict[str, Literal["class", "teacher"]] = Field(default_factory=dict)
    special_subjects: list[str] = Field(default_factory=list)
    calendar_closures: list[CalendarClosureInput] = Field(default_factory=list)


class UpdateTimetableRequest(BaseModel):
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    effective_ranges: Optional[list[TimetableDateRange]] = Field(default=None, min_length=1)
    special_subjects: Optional[list[str]] = None


class SaveImportResolutionsRequest(BaseModel):
    resolutions: dict[str, Literal["class", "teacher"]] = Field(min_length=1)


class AbsenceCreateRequest(BaseModel):
    professor_id: int
    data: date
    periods: list[int] = Field(min_length=1)
    reason_type: Literal["sick", "follow_up", "team_training", "other", "personal", "official", "training"]
    reason_detail: Optional[str] = None

    @model_validator(mode="after")
    def normalize_reason(self):
        detail = (self.reason_detail or "").strip() or None
        if detail and len(detail) > 200:
            raise ValueError("其他原因最多 200 字")
        self.reason_detail = detail if self.reason_type == "other" else None
        return self


class AbsenceBatchCreateRequest(BaseModel):
    items: list[AbsenceCreateRequest] = Field(min_length=1, max_length=3)


class AbsenceBatchCancelRequest(BaseModel):
    absence_case_ids: list[int] = Field(min_length=1)


class ConfirmRequest(BaseModel):
    absence_case_id: int
    candidate_id: str
    expected_revision: int
    reason: Optional[str] = None


class ManualCoverRequest(BaseModel):
    absence_case_id: int
    occurrence_id: str
    replacement_teacher_id: Optional[int] = None
    co_teacher_only: bool = False
    expected_revision: int
    reason: Optional[str] = Field(default=None, max_length=500)


class UpdateAdjustmentRequest(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=500)


class ManualLegRequest(BaseModel):
    occurrence_id: str
    from_date: date
    to_date: date
    to_period: int = Field(ge=1, le=9)


class ManualAdjustmentRequest(BaseModel):
    legs: list[ManualLegRequest] = Field(min_length=2, max_length=3)
    expected_revision: int
    reason: str


class ClosureInput(BaseModel):
    data: date
    note: Optional[str] = None


class ClosureListRequest(BaseModel):
    closures: list[ClosureInput]
    year: int


class TeacherLeaveRequest(BaseModel):
    professor_id: int
    start_date: date
    end_date: date
    leave_type: str


class PeriodTimeInput(BaseModel):
    period: int = Field(ge=1, le=9)
    start: str
    end: str


class PeriodTimesRequest(BaseModel):
    periods: list[PeriodTimeInput] = Field(min_length=9, max_length=9)


class ReschedulingConfigRequest(BaseModel):
    max_cycle_lessons: int = Field(ge=2, le=5)


def _audit(db: Session, action: str, entity_type: str, entity_id, username: str, detail=None):
    db.add(ScheduleAudit(
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        username=username,
        detail_json=json.dumps(detail or {}, ensure_ascii=False),
    ))


def _absence_reason_payload(absence: AbsenceCase) -> dict:
    return {"reason_type": absence.reason_type, "reason_detail": absence.reason_detail}


def _period_starts(db: Session, day: date | None = None) -> dict[int, str]:
    return {int(item["period"]): item["start"] for item in get_period_times(db, day)}


def _analyze_current(db: Session, absences: list[AbsenceCase]) -> dict:
    return analyze_absences(
        db, absences, now=hong_kong_now(), period_starts=_period_starts(db, absences[0].data)
    )


def _adjustment_execution_state(db: Session, legs: list[ScheduleAdjustmentLeg]) -> str:
    now = hong_kong_now()
    slots = {
        (day, period)
        for leg in legs
        for day, period in ((leg.from_date, leg.from_period), (leg.to_date, leg.to_period))
    }
    started = sum(schedule_slot_started(day, period, now, _period_starts(db, day)) for day, period in slots)
    if not started:
        return "pending"
    return "completed" if started == len(slots) else "partial"


def _serialize_adjustment(db: Session, adjustment: ScheduleAdjustment) -> dict:
    professor_names = {row.id: row.nom for row in db.query(Professor).all()}
    legs = db.query(ScheduleAdjustmentLeg).filter_by(adjustment_id=adjustment.id).order_by(ScheduleAdjustmentLeg.id).all()
    execution_state = _adjustment_execution_state(db, legs)
    has_downstream = adjustment.status == "confirmed" and _has_confirmed_downstream_adjustment(
        db, adjustment, legs
    )
    return {
        "id": adjustment.id,
        "absence_case_id": adjustment.absence_case_id,
        "kind": adjustment.kind,
        "status": adjustment.status,
        "locked": adjustment.locked,
        "needs_review": bool(adjustment.needs_review),
        "reason": adjustment.reason,
        "confirmed_by": adjustment.confirmed_by,
        "confirmed_at": utc_iso(adjustment.confirmed_at),
        "reverted_by": adjustment.reverted_by,
        "reverted_at": utc_iso(adjustment.reverted_at),
        "execution_state": execution_state,
        "can_revert": adjustment.status == "confirmed" and execution_state == "pending" and not has_downstream,
        "legs": [{
            "lesson_id": leg.lesson_id,
            "class_code": leg.class_code,
            "subject": leg.subject,
            "teacher_ids": json.loads(leg.teachers_json or "[]"),
            "teacher_names": [professor_names.get(value, str(value)) for value in json.loads(leg.teachers_json or "[]")],
            "from_date": leg.from_date.isoformat(),
            "from_period": leg.from_period,
            "to_date": leg.to_date.isoformat(),
            "to_period": leg.to_period,
            "replaced_teacher_id": leg.replaced_teacher_id,
            "replacement_teacher_id": leg.replacement_teacher_id,
            "replacement_teacher_name": professor_names.get(leg.replacement_teacher_id) if leg.replacement_teacher_id else None,
        } for leg in legs],
    }


def _serialize_leave(row: ProfessorBaixa, professor_ids: dict[str, int]) -> dict:
    return {
        "id": row.id,
        "professor_id": professor_ids.get(row.professor),
        "teacher_name": row.professor,
        "start_date": row.data_inici.isoformat(),
        "end_date": row.data_final.isoformat(),
        "leave_type": row.motiu or "other",
    }


def _request_ranges(request, post_exam: bool, version: TimetableVersion | None = None):
    if request.effective_ranges is not None:
        ranges = sorted((row.effective_from, row.effective_to) for row in request.effective_ranges)
    else:
        if version and len(version_ranges(version)) > 1:
            raise HTTPException(409, "此試後課表有多個適用時段，請提交完整時段清單")
        if request.effective_from is None or request.effective_to is None:
            raise HTTPException(400, "請填寫開始及結束日期")
        ranges = [(request.effective_from, request.effective_to)]
    if not post_exam and len(ranges) > 1:
        raise HTTPException(400, "只有試後課表可以設定多個適用時段")
    if any(start > end for start, end in ranges):
        raise HTTPException(400, "結束日期不可早於開始日期")
    if any(current[0] <= previous[1] for previous, current in zip(ranges, ranges[1:])):
        raise HTTPException(400, "同一課表的適用時段不可重疊")
    request.effective_from, request.effective_to = ranges[0][0], ranges[-1][1]
    return ranges


def _records_in_range(db: Session, start: date, end: date | None) -> tuple[int, set[int]]:
    absences = db.query(AbsenceCase).filter(AbsenceCase.data >= start)
    if end:
        absences = absences.filter(AbsenceCase.data <= end)
        leg_dates = or_(
            and_(ScheduleAdjustmentLeg.from_date >= start, ScheduleAdjustmentLeg.from_date <= end),
            and_(ScheduleAdjustmentLeg.to_date >= start, ScheduleAdjustmentLeg.to_date <= end),
        )
    else:
        leg_dates = or_(ScheduleAdjustmentLeg.from_date >= start, ScheduleAdjustmentLeg.to_date >= start)
    adjustment_ids = {row[0] for row in
                      db.query(ScheduleAdjustmentLeg.adjustment_id).filter(leg_dates).distinct().all()}
    return absences.count(), adjustment_ids


def _version_usage(db: Session, version: TimetableVersion) -> tuple[int, int]:
    absences, adjustment_ids = 0, set()
    for start, end in version_ranges(version):
        count, ids = _records_in_range(db, start, end)
        absences += count
        adjustment_ids.update(ids)
    adjustment_ids.update(row[0] for row in
                          db.query(ScheduleAdjustmentLeg.adjustment_id)
                          .join(TimetableLesson, ScheduleAdjustmentLeg.lesson_id == TimetableLesson.id)
                          .filter(TimetableLesson.version_id == version.id).distinct().all())
    return absences, len(adjustment_ids)


def _overlapping_version(db: Session, start: date, end: date, exclude_id: int | None = None):
    query = db.query(TimetableVersion).filter(
        TimetableVersion.effective_from <= end,
        or_(TimetableVersion.effective_to.is_(None), TimetableVersion.effective_to >= start),
    )
    if exclude_id is not None:
        query = query.filter(TimetableVersion.id != exclude_id)
    return next((version for version in query.all()
                 if any(left <= end and (right is None or right >= start)
                        for left, right in version_ranges(version))), None)


def _version_record_dates(db: Session, version: TimetableVersion) -> set[date]:
    ranges = version_ranges(version)
    dates = {row[0] for row in db.query(AbsenceCase.data)
             .filter(AbsenceCase.data >= version.effective_from).all()
             if matching_range_start(ranges, row[0]) is not None}
    lesson_ids = {row[0] for row in db.query(TimetableLesson.id).filter_by(version_id=version.id).all()}
    for leg in db.query(ScheduleAdjustmentLeg).all():
        if leg.lesson_id in lesson_ids:
            dates.add(leg.from_date)
        for value in (leg.from_date, leg.to_date):
            if matching_range_start(ranges, value) is not None:
                dates.add(value)
    return dates


def _check_added_range_records(db: Session, old_ranges, new_ranges):
    # Check actual record dates, including both ends of swaps, without filling interval gaps.
    start, end = new_ranges[0][0], new_ranges[-1][1]
    dates = {row[0] for row in db.query(AbsenceCase.data)
             .filter(AbsenceCase.data >= start, AbsenceCase.data <= end).all()}
    for left, right in db.query(ScheduleAdjustmentLeg.from_date, ScheduleAdjustmentLeg.to_date).filter(
        or_(ScheduleAdjustmentLeg.from_date.between(start, end),
            ScheduleAdjustmentLeg.to_date.between(start, end))
    ).all():
        dates.update((left, right))
    if any(matching_range_start(new_ranges, day) is not None
           and matching_range_start(old_ranges, day) is None for day in dates):
        raise HTTPException(409, "新增適用時段已有缺席或調課記錄，不能覆蓋")


def _mark_latest_version_active(db: Session) -> None:
    latest = (db.query(TimetableVersion)
              .order_by(TimetableVersion.effective_from.desc(), TimetableVersion.id.desc()).first())
    for row in db.query(TimetableVersion).all():
        row.active = bool(latest and row.id == latest.id)


def _mark_special_adjustments_for_review(db: Session, version: TimetableVersion,
                                         changed_subjects: set[str]) -> int:
    if not changed_subjects:
        return 0
    adjustment_ids = {
        row[0] for row in (
            db.query(ScheduleAdjustmentLeg.adjustment_id)
            .join(ScheduleAdjustment, ScheduleAdjustmentLeg.adjustment_id == ScheduleAdjustment.id)
            .join(TimetableLesson, ScheduleAdjustmentLeg.lesson_id == TimetableLesson.id)
            .filter(
                ScheduleAdjustment.status == "confirmed",
                TimetableLesson.version_id == version.id,
                ScheduleAdjustmentLeg.subject.in_(changed_subjects),
                ScheduleAdjustmentLeg.from_date != ScheduleAdjustmentLeg.to_date,
            )
            .distinct().all()
        )
    }
    if not adjustment_ids:
        return 0
    now = hong_kong_now()
    def unfinished(day: date, period: int) -> bool:
        if day != now.date():
            return day > now.date()
        period_ends = {item["period"]: item["end"] for item in get_period_times(db, day)}
        hour, minute = map(int, period_ends[int(period)].split(":"))
        return (now.hour, now.minute) < (hour, minute)

    marked = 0
    for adjustment in db.query(ScheduleAdjustment).filter(ScheduleAdjustment.id.in_(adjustment_ids)).all():
        legs = db.query(ScheduleAdjustmentLeg).filter_by(adjustment_id=adjustment.id).all()
        if any(unfinished(day, period) for leg in legs for day, period in (
            (leg.from_date, leg.from_period), (leg.to_date, leg.to_period)
        )) and not adjustment.needs_review:
            adjustment.needs_review = True
            marked += 1
    return marked


@router.get("/api/timetable-groups")
def list_timetable_groups(
    db: Session = Depends(get_db),
    _current_user=Depends(require_any_permission("workbench.view", "timetable.upload", "timetable.manage")),
):
    return [{"id": group.id, "name": group.name}
            for group in db.query(TimetableGroup).order_by(TimetableGroup.name.desc(), TimetableGroup.id.desc()).all()]


@router.post("/api/timetable-groups")
def create_timetable_group(
    request: TimetableGroupRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("timetable.manage")),
):
    group = TimetableGroup(name=request.name)
    db.add(group)
    try:
        db.flush()
        _audit(db, "create", "timetable_group", group.id, current_user.username, {"name": group.name})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "已有同名分組，請使用另一個名稱")
    return {"id": group.id, "name": group.name}


@router.put("/api/timetable-groups/{group_id}")
def rename_timetable_group(
    group_id: int,
    request: TimetableGroupRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("timetable.manage")),
):
    group = db.get(TimetableGroup, group_id)
    if not group:
        raise HTTPException(404, "找不到分組")
    old_name = group.name
    group.name = request.name
    try:
        db.flush()
        _audit(db, "update", "timetable_group", group.id, current_user.username,
               {"old_name": old_name, "name": group.name})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "已有同名分組，請使用另一個名稱")
    return {"id": group.id, "name": group.name}


@router.put("/api/timetables/{version_id}/group")
def move_timetable_group(
    version_id: int,
    request: MoveTimetableGroupRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("timetable.manage")),
):
    version = db.get(TimetableVersion, version_id)
    if not version:
        raise HTTPException(404, "找不到課表版本")
    if request.group_id is not None and not db.get(TimetableGroup, request.group_id):
        raise HTTPException(404, "找不到分組")
    old_group_id = version.group_id
    version.group_id = request.group_id
    _audit(db, "update", "timetable_group_membership", version.id, current_user.username,
           {"old_group_id": old_group_id, "group_id": version.group_id})
    db.commit()
    return {"id": version.id, "group_id": version.group_id}


@router.get("/api/timetables")
def list_timetable_versions(
    db: Session = Depends(get_db),
    _current_user=Depends(require_any_permission(
        "workbench.view", "timetable.upload", "timetable.manage"
    )),
):
    versions = (db.query(TimetableVersion)
                .order_by(TimetableVersion.effective_from.desc(), TimetableVersion.id.desc()).all())
    current = version_for_date(db, hong_kong_today())
    rows = []
    for version in versions:
        absences, adjustments = _version_usage(db, version)
        lessons = db.query(TimetableLesson).filter_by(version_id=version.id).all()
        rows.append({
            "id": version.id,
            "group_id": version.group_id,
            "effective_from": version.effective_from.isoformat(),
            "effective_to": version.effective_to.isoformat() if version.effective_to else None,
            "effective_ranges": serialize_ranges(version_ranges(version)),
            "class_filename": version.class_filename,
            "teacher_filename": version.teacher_filename,
            "post_exam": is_post_exam_version(version),
            "resolution_count": len(json.loads(version.resolutions_json or "{}")),
            "lessons": len(lessons),
            "subjects": sorted({lesson.subject for lesson in lessons}),
            "special_subjects": sorted({lesson.subject for lesson in lessons if lesson.special}),
            "teachers": (db.query(func.count(func.distinct(TimetableTeacherSlot.professor_id)))
                         .filter(TimetableTeacherSlot.version_id == version.id).scalar() or 0),
            "absence_records": absences,
            "adjustment_records": adjustments,
            "locked": bool(absences or adjustments),
            "is_current": bool(current and current.id == version.id),
            "created_by": version.created_by,
            "created_at": utc_iso(version.created_at),
        })
    return rows


@router.put("/api/timetables/{version_id}")
def update_timetable_version(
    version_id: int,
    request: UpdateTimetableRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("timetable.manage")),
):
    version = db.get(TimetableVersion, version_id)
    if not version:
        raise HTTPException(404, "找不到課表版本")
    ranges = _request_ranges(request, is_post_exam_version(version), version)
    lessons = db.query(TimetableLesson).filter_by(version_id=version.id).all()
    current_specials = {lesson.subject for lesson in lessons if lesson.special}
    requested_specials = set(request.special_subjects) if request.special_subjects is not None else current_specials
    available_subjects = {lesson.subject for lesson in lessons}
    if not requested_specials.issubset(available_subjects):
        raise HTTPException(400, "包含課表中不存在的特殊課程")
    old_ranges = version_ranges(version)
    dates_changed = ranges != old_ranges
    specials_changed = requested_specials != current_specials
    if not dates_changed and not specials_changed:
        return {"success": True, "revision": get_schedule_revision(db)}
    if (dates_changed and not is_post_exam_version(version)
            and _overlapping_version(db, request.effective_from, request.effective_to, version.id)):
        raise HTTPException(409, "課表適用日期與另一個版本重疊")
    if dates_changed:
        record_dates = _version_record_dates(db, version)
        if any(matching_range_start(ranges, value) is None for value in record_dates):
            raise HTTPException(409, "新日期範圍未能包含此版本的全部缺席或調課記錄")
        _check_added_range_records(db, old_ranges, ranges)
    old_range = {"effective_from": version.effective_from.isoformat(),
                 "effective_to": version.effective_to.isoformat() if version.effective_to else None,
                 "effective_ranges": serialize_ranges(old_ranges)}
    version.effective_from = request.effective_from
    version.effective_to = request.effective_to
    version.effective_ranges_json = json.dumps(serialize_ranges(ranges)) if is_post_exam_version(version) else None
    for lesson in lessons:
        lesson.special = lesson.subject in requested_specials
    review_required_count = _mark_special_adjustments_for_review(
        db, version, current_specials ^ requested_specials
    )
    _mark_latest_version_active(db)
    revision = bump_schedule_revision(db)
    _audit(db, "update", "timetable_version", version.id, current_user.username,
           {"old": old_range, "effective_from": request.effective_from.isoformat(),
            "effective_to": request.effective_to.isoformat(),
            "effective_ranges": serialize_ranges(ranges),
            "old_special_subjects": sorted(current_specials),
            "special_subjects": sorted(requested_specials),
            "review_required_count": review_required_count})
    db.commit()
    return {"success": True, "revision": revision, "review_required_count": review_required_count}


@router.delete("/api/timetables/{version_id}")
def delete_timetable_version(
    version_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("timetable.manage")),
):
    version = db.get(TimetableVersion, version_id)
    if not version:
        raise HTTPException(404, "找不到課表版本")
    if any(_version_usage(db, version)):
        raise HTTPException(409, "此版本已牽涉缺席或調課記錄，不能刪除")
    db.query(TimetableTeacherSlot).filter_by(version_id=version.id).delete(synchronize_session=False)
    db.query(TimetableLesson).filter_by(version_id=version.id).delete(synchronize_session=False)
    db.delete(version)
    db.flush()
    _mark_latest_version_active(db)
    revision = bump_schedule_revision(db)
    _audit(db, "delete", "timetable_version", version_id, current_user.username,
           {"effective_from": version.effective_from.isoformat(),
            "effective_to": version.effective_to.isoformat() if version.effective_to else None,
            "effective_ranges": serialize_ranges(version_ranges(version))})
    db.commit()
    return {"success": True, "revision": revision}


@router.post("/api/timetables/import/preview")
async def preview_import(
    class_workbook: UploadFile = File(...),
    teacher_workbook: UploadFile = File(...),
    calendar_docx: Optional[UploadFile] = File(None),
    schedule_type: str = Form("normal"),
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("timetable.upload")),
):
    if schedule_type not in {"normal", "post_exam"}:
        raise HTTPException(400, "不支援的課表類型")
    class_extension = ".xlsx" if schedule_type == "post_exam" else ".xls"
    if not (class_workbook.filename or "").lower().endswith(class_extension):
        raise HTTPException(400, f"班別時間表必須是 {class_extension}")
    if not (teacher_workbook.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(400, "教師時間表必須是 .xlsx（請使用非值日版本）")
    if calendar_docx and not (calendar_docx.filename or "").lower().endswith(".docx"):
        raise HTTPException(400, "校曆必須是 .docx")
    if calendar_docx and getattr(current_user, "role", None) not in {"admin", "super_admin"}:
        raise HTTPException(403, "只有管理員可匯入校曆假期")
    class_content = await class_workbook.read(MAX_UPLOAD_BYTES + 1)
    teacher_content = await teacher_workbook.read(MAX_UPLOAD_BYTES + 1)
    if len(class_content) > MAX_UPLOAD_BYTES or len(teacher_content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "課表檔案不可超過 12 MB")
    calendar_content = await calendar_docx.read(MAX_UPLOAD_BYTES + 1) if calendar_docx else None
    if calendar_content is not None and len(calendar_content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "校曆檔案不可超過 12 MB")
    try:
        payload = build_import_preview(
            class_content, teacher_content, post_exam=schedule_type == "post_exam"
        )
    except Exception as exc:
        raise HTTPException(400, f"無法讀取課表：{exc}") from exc
    calendar = None
    if calendar_content is not None:
        try:
            calendar = parse_calendar_docx(calendar_content)
        except Exception as exc:
            raise HTTPException(400, f"無法讀取校曆：{exc}") from exc
        payload["calendar"] = calendar
    preview_id = uuid.uuid4().hex
    db.add(TimetableImportPreview(
        id=preview_id,
        payload=json.dumps(payload, ensure_ascii=False),
        class_filename=class_workbook.filename,
        teacher_filename=teacher_workbook.filename,
        created_by=current_user.username,
    ))
    audit_detail = dict(payload["summary"])
    if calendar:
        audit_detail["calendar"] = {
            "school_year": calendar.get("school_year"),
            "calendar_start": calendar.get("calendar_start"),
            "calendar_end": calendar.get("calendar_end"),
            "closures": len(calendar.get("closures", [])),
            "warnings": len(calendar.get("warnings", [])),
        }
    _audit(db, "preview_import", "timetable_preview", preview_id, current_user.username, audit_detail)
    db.commit()
    return {"preview_id": preview_id, **payload["summary"], "warnings": payload["warnings"],
            "issues": payload["issues"],
            "calendar": calendar,
            "post_exam": payload.get("format") == "post_exam",
            "subjects": sorted({lesson["subject"] for lesson in payload["lessons"]})}


@router.post("/api/timetables/import/{preview_id}/activate")
def activate_import(
    preview_id: str,
    request: ActivateTimetableRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("timetable.manage")),
):
    preview = db.get(TimetableImportPreview, preview_id)
    if not preview:
        raise HTTPException(404, "找不到匯入預覽，請重新選擇檔案")
    payload = json.loads(preview.payload)
    calendar_closures = {
        item.date: (item.note or "").strip() or None
        for item in request.calendar_closures
    }
    calendar = payload.get("calendar")
    if calendar_closures:
        if getattr(current_user, "role", None) not in {"admin", "super_admin"}:
            raise HTTPException(403, "只有管理員可匯入校曆假期")
        if not calendar:
            raise HTTPException(400, "此預覽沒有校曆資料")
        try:
            calendar_start = date.fromisoformat(calendar["calendar_start"])
            calendar_end = date.fromisoformat(calendar["calendar_end"])
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(409, "校曆預覽資料無效，請重新上傳") from exc
        if any(day < calendar_start or day > calendar_end for day in calendar_closures):
            raise HTTPException(400, "假期日期必須位於校曆涵蓋範圍內")
    if any(issue["severity"] == "error" for issue in payload["issues"]):
        raise HTTPException(409, "仍有必須在原 Excel 修正的錯誤")
    resolutions = payload.get("saved_resolutions", request.resolutions)
    try:
        payload = apply_import_resolutions(payload, resolutions)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    available_subjects = {lesson["subject"] for lesson in payload["lessons"]}
    special_subjects = set(request.special_subjects)
    if not special_subjects.issubset(available_subjects):
        raise HTTPException(400, "包含課表中不存在的特殊課程")
    ranges = _request_ranges(request, payload.get("format") == "post_exam")
    if payload.get("format") != "post_exam" and _overlapping_version(
        db, request.effective_from, request.effective_to
    ):
        raise HTTPException(409, "課表適用日期與另一個版本重疊")
    _check_added_range_records(db, [], ranges)
    version = TimetableVersion(
        effective_from=request.effective_from,
        effective_to=request.effective_to,
        effective_ranges_json=json.dumps(serialize_ranges(ranges)) if payload.get("format") == "post_exam" else None,
        class_filename=preview.class_filename,
        teacher_filename=preview.teacher_filename,
        resolutions_json=json.dumps(resolutions, ensure_ascii=False),
        active=False,
        created_by=current_user.username,
    )
    db.add(version)
    db.flush()

    active_names = set(payload["teachers"])
    for professor in db.query(Professor).all():
        professor.actiu = professor.nom in active_names
    professor_ids: dict[str, int] = {}
    for name in sorted(active_names):
        professor = db.query(Professor).filter_by(nom=name).first()
        if not professor:
            professor = Professor(nom=name, actiu=True, primera_aparicio=request.effective_from)
            db.add(professor)
            db.flush()
        professor.actiu = True
        professor.ultima_aparicio = request.effective_from
        professor_ids[name] = professor.id

    for lesson in payload["lessons"]:
        db.add(TimetableLesson(
            version_id=version.id,
            weekday=lesson["weekday"],
            period=lesson["period"],
            class_code=lesson["class_code"],
            subject=lesson["subject"],
            teachers_json=json.dumps([professor_ids[name] for name in lesson["teachers"] if name in professor_ids]),
            movable=lesson.get("movable", True),
            special=lesson["subject"] in special_subjects,
        ))
    for slot in payload["teacher_slots"]:
        if slot["teacher"] not in professor_ids:
            continue
        db.add(TimetableTeacherSlot(
            version_id=version.id,
            professor_id=professor_ids[slot["teacher"]],
            weekday=slot["weekday"],
            period=slot["period"],
            class_code=slot["class_code"],
            subject=slot["subject"],
        ))
    created_closures = 0
    for closure_date, note in sorted(calendar_closures.items()):
        closure = db.get(SchoolClosure, closure_date)
        if closure:
            if not closure.note and note:
                closure.note = note
        else:
            db.add(SchoolClosure(
                data=closure_date, note=note, created_by=current_user.username,
            ))
            created_closures += 1
    db.delete(preview)
    _mark_latest_version_active(db)
    revision = bump_schedule_revision(db)
    audit_detail = {
        **payload["summary"], "resolutions": resolutions,
        "effective_ranges": serialize_ranges(ranges),
        "special_subjects": sorted(special_subjects),
    }
    if calendar:
        audit_detail["calendar"] = {
            "school_year": calendar.get("school_year"),
            "selected_closures": len(calendar_closures),
            "created_closures": created_closures,
            "dates": [value.isoformat() for value in sorted(calendar_closures)],
        }
    _audit(db, "activate_import", "timetable_version", version.id, current_user.username,
           audit_detail)
    db.commit()
    return {"version_id": version.id, "revision": revision, **payload["summary"],
             "warnings": payload["warnings"], "issues": payload.get("issues", []),
             "calendar_closures": len(calendar_closures)}


@router.delete("/api/timetables/import/{preview_id}")
def discard_import_preview(
    preview_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("timetable.upload")),
):
    preview = db.get(TimetableImportPreview, preview_id)
    if not preview:
        raise HTTPException(404, "找不到匯入預覽")
    db.delete(preview)
    _audit(db, "discard_import", "timetable_preview", preview_id, current_user.username)
    db.commit()
    return {"success": True}


@router.put("/api/timetables/import/{preview_id}/resolutions")
def save_import_resolutions(
    preview_id: str,
    request: SaveImportResolutionsRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("timetable.upload")),
):
    preview = db.get(TimetableImportPreview, preview_id)
    if not preview:
        raise HTTPException(404, "找不到匯入預覽，請重新選擇檔案")
    payload = json.loads(preview.payload)
    review_ids = {
        issue["resolution_id"]
        for issue in payload["issues"]
        if issue["severity"] == "review"
    }
    if not set(request.resolutions).issubset(review_ids):
        raise HTTPException(400, "包含無效的核對項目")
    saved = {**payload.get("saved_resolutions", {}), **request.resolutions}
    payload["saved_resolutions"] = saved
    preview.payload = json.dumps(payload, ensure_ascii=False)
    _audit(db, "save_resolutions", "timetable_preview", preview_id, current_user.username,
           {"confirmed": len(saved), "remaining": len(review_ids - set(saved))})
    db.commit()
    return {
        "saved_resolutions": saved,
        "confirmed_count": len(saved),
        "remaining_count": len(review_ids - set(saved)),
    }


@router.get("/api/timetables/current")
def current_timetable(
    data: Optional[date] = None,
    db: Session = Depends(get_db),
    _current_user=Depends(require_any_permission(
        "workbench.view", "timetable.upload", "timetable.manage"
    )),
):
    query_date = data or hong_kong_today()
    version = version_for_date(db, query_date)
    if not version:
        return {"active": False, "query_date": query_date.isoformat(), "revision": get_schedule_revision(db)}
    return {
        "active": True,
        "query_date": query_date.isoformat(),
        "version_id": version.id,
        "effective_from": version.effective_from.isoformat(),
        "effective_to": version.effective_to.isoformat() if version.effective_to else None,
        "effective_ranges": serialize_ranges(version_ranges(version)),
        "class_filename": version.class_filename,
        "teacher_filename": version.teacher_filename,
        "post_exam": is_post_exam_version(version),
        "period_count": len(get_period_times(db, query_date)),
        "lessons": db.query(TimetableLesson).filter_by(version_id=version.id).count(),
        "revision": get_schedule_revision(db),
    }


@router.get("/api/rescheduling/teachers")
def list_teachers(
    data: Optional[date] = None,
    db: Session = Depends(get_db),
    _current_user=Depends(require_any_permission("workbench.view", "records.manage")),
):
    version = version_for_date(db, data or hong_kong_today())
    if not version:
        if data is not None:
            return []
        return [{"id": row.id, "name": row.nom} for row in
                db.query(Professor).filter_by(actiu=True).order_by(Professor.nom).all()]
    teacher_ids = professor_ids_for_version(db, version)
    return [{"id": row.id, "name": row.nom} for row in
                db.query(Professor).filter(Professor.id.in_(teacher_ids)).order_by(Professor.nom).all()]


@router.get("/api/rescheduling/statistics")
def teacher_statistics(
    start_date: date,
    end_date: date,
    db: Session = Depends(get_db),
    _current_user=Depends(require_permission("statistics.view")),
):
    if start_date > end_date:
        raise HTTPException(400, "結束日期不可早於開始日期")
    start, end = start_date, end_date
    month_keys = []
    cursor = date(start.year, start.month, 1)
    last_month = date(end.year, end.month, 1)
    while cursor <= last_month:
        month_keys.append(cursor.strftime("%Y-%m"))
        cursor = date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)

    counts: dict[int, dict[str, int]] = {}
    rows = (
        db.query(ScheduleAdjustmentLeg, ScheduleAdjustment, AbsenceCase)
        .join(ScheduleAdjustment, ScheduleAdjustmentLeg.adjustment_id == ScheduleAdjustment.id)
        .join(AbsenceCase, ScheduleAdjustment.absence_case_id == AbsenceCase.id)
        .filter(
            ScheduleAdjustment.status == "confirmed",
            ScheduleAdjustmentLeg.to_date >= start,
            ScheduleAdjustmentLeg.to_date <= end,
        )
        .order_by(ScheduleAdjustment.id, ScheduleAdjustmentLeg.to_date, ScheduleAdjustmentLeg.id)
        .all()
    )
    counted: set[tuple[int, int]] = set()
    for leg, adjustment, absence in rows:
        if adjustment.kind == "co_teacher_solo":
            continue
        teacher_ids = (
            {leg.replacement_teacher_id}
            if adjustment.kind == "emergency_cover" and leg.replacement_teacher_id
            else {int(value) for value in json.loads(leg.teachers_json or "[]")}
        )
        teacher_ids.discard(absence.professor_id)
        month = leg.to_date.strftime("%Y-%m")
        for teacher_id in teacher_ids:
            key = (adjustment.id, teacher_id)
            if key in counted:
                continue
            counted.add(key)
            counts.setdefault(teacher_id, {}).setdefault(month, 0)
            counts[teacher_id][month] += 1

    teachers = db.query(Professor).order_by(Professor.nom).all()
    return {
        "range": {
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        },
        "months": month_keys,
        "teachers": [{
            "id": teacher.id,
            "name": teacher.nom,
            "monthly": {month: counts.get(teacher.id, {}).get(month, 0) for month in month_keys},
            "total": sum(counts.get(teacher.id, {}).values()),
        } for teacher in teachers],
    }


@router.get("/api/rescheduling/period-times")
def period_time_settings(db: Session = Depends(get_db), _current_user=Depends(require_admin)):
    return {"periods": get_period_times(db)}


@router.put("/api/rescheduling/period-times")
def update_period_time_settings(
    request: PeriodTimesRequest,
    db: Session = Depends(get_db),
    _current_user=Depends(require_admin),
):
    try:
        periods = save_period_times(db, [item.model_dump() for item in request.periods])
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    return {"periods": periods}


@router.get("/api/rescheduling/config")
def rescheduling_config(db: Session = Depends(get_db), _current_user=Depends(require_admin)):
    return {"max_cycle_lessons": get_max_cycle_lessons(db)}


@router.put("/api/rescheduling/config")
def update_rescheduling_config(
    request: ReschedulingConfigRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    if get_max_cycle_lessons(db) == request.max_cycle_lessons:
        return {"max_cycle_lessons": request.max_cycle_lessons,
                "revision": get_schedule_revision(db)}
    row = db.get(Configuracio, MAX_CYCLE_LESSONS_KEY)
    if row:
        row.valor = str(request.max_cycle_lessons)
        row.tipus = "integer"
    else:
        db.add(Configuracio(
            clau=MAX_CYCLE_LESSONS_KEY,
            valor=str(request.max_cycle_lessons),
            tipus="integer",
            descripcio="自動分析最大連鎖調課堂數",
        ))
    revision = bump_schedule_revision(db)
    _audit(db, "update", "rescheduling_config", None, current_user.username,
           {"max_cycle_lessons": request.max_cycle_lessons})
    db.commit()
    return {"max_cycle_lessons": request.max_cycle_lessons, "revision": revision}


@router.get("/api/rescheduling/exports/daily.xlsx")
def export_daily_xlsx(
    data: date,
    db: Session = Depends(get_db),
    _current_user=Depends(require_permission("exports.download")),
):
    entries = daily_export_data(db, data)
    if not entries:
        raise HTTPException(404, "所選日期沒有可匯出的調課／代課記錄")
    content = build_daily_xlsx(entries, get_period_times(db, data))
    return StreamingResponse(
        BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="daily-substitution-{data.isoformat()}.xlsx"'},
    )


@router.get("/api/rescheduling/exports/daily.pdf")
def export_daily_pdf(
    data: date,
    db: Session = Depends(get_db),
    _current_user=Depends(require_permission("exports.download")),
):
    entries = daily_export_data(db, data)
    if not entries:
        raise HTTPException(404, "所選日期沒有可匯出的調課／代課記錄")
    content = build_daily_pdf(entries, get_period_times(db, data))
    return StreamingResponse(
        BytesIO(content), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="daily-substitution-{data.isoformat()}.pdf"'},
    )


def _validate_absence_request(
    db: Session,
    request: AbsenceCreateRequest,
    exclude_id: int | None = None,
    allow_existing: bool = False,
):
    version = version_for_date(db, request.data)
    if not version:
        raise HTTPException(400, "該日期沒有已生效的課表版本")
    professor = db.get(Professor, request.professor_id)
    if not professor or request.professor_id not in professor_ids_for_version(db, version):
        raise HTTPException(404, "找不到教師")
    periods = sorted(set(request.periods))
    max_period = len(get_period_times(db, request.data))
    if any(period < 1 or period > max_period for period in periods):
        raise HTTPException(400, f"節次必須介乎 1 至 {max_period}")
    if request.data.weekday() >= 5 or db.get(SchoolClosure, request.data):
        raise HTTPException(400, "所選日期不是上課日")
    duplicate = (db.query(AbsenceCase)
                 .filter(AbsenceCase.professor_id == professor.id, AbsenceCase.data == request.data,
                         AbsenceCase.status != "cancelled"))
    if exclude_id is not None:
        duplicate = duplicate.filter(AbsenceCase.id != exclude_id)
    if duplicate.first() and not allow_existing:
        raise HTTPException(409, "該教師當日已有缺席紀錄")
    return professor, periods


def _active_absences_for_date(db: Session, target_date: date) -> list[AbsenceCase]:
    return (db.query(AbsenceCase)
            .filter(AbsenceCase.data == target_date, AbsenceCase.status != "cancelled")
            .order_by(AbsenceCase.id).all())


def _professors_with_lessons(db: Session, target_date: date, periods: list[int]) -> set[int]:
    selected_periods = set(periods)
    return {
        int(professor_id)
        for occurrence in effective_occurrences(db, target_date, target_date)
        if occurrence["lesson_id"] is not None and occurrence["period"] in selected_periods
        for professor_id in occurrence["teachers"]
    }


def _delete_adjustment_rows(db: Session, adjustment: ScheduleAdjustment) -> None:
    db.query(ScheduleAdjustmentLeg).filter_by(adjustment_id=adjustment.id).delete(synchronize_session=False)
    db.delete(adjustment)


def _has_confirmed_downstream_adjustment(
    db: Session, adjustment: ScheduleAdjustment, legs: list[ScheduleAdjustmentLeg]
) -> bool:
    destinations = {(leg.lesson_id, leg.to_date, leg.to_period) for leg in legs}
    later_legs = (
        db.query(ScheduleAdjustmentLeg)
        .join(ScheduleAdjustment, ScheduleAdjustmentLeg.adjustment_id == ScheduleAdjustment.id)
        .filter(
            ScheduleAdjustment.status == "confirmed",
            ScheduleAdjustment.id > adjustment.id,
        )
        .all()
    )
    return any((leg.lesson_id, leg.from_date, leg.from_period) in destinations for leg in later_legs)


def _can_manage_records(current_user) -> bool:
    # Direct service-level callers predate route dependencies and omit role;
    # authenticated ORM users always have it.
    if not hasattr(current_user, "role"):
        return current_user.username == "admin"
    return (
        user_has_permission(current_user, "records.view")
        and user_has_permission(current_user, "records.manage")
    )


def _ensure_absence_editable(current_user, absence: AbsenceCase) -> bool:
    can_manage_records = _can_manage_records(current_user)
    if not can_manage_records and absence.created_by != current_user.username:
        raise HTTPException(403, "只可修改或撤回自己建立的缺席紀錄")
    return can_manage_records


@router.post("/api/absence-cases")
def create_absence(
    request: AbsenceCreateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("absence.create")),
):
    professor, periods = _validate_absence_request(db, request)
    if professor.id not in _professors_with_lessons(db, request.data, periods):
        raise HTTPException(400, "所選節次沒有需要處理的課堂")
    absence = AbsenceCase(
        professor_id=professor.id,
        data=request.data,
        periods_json=json.dumps(periods),
        reason_type=request.reason_type,
        reason_detail=request.reason_detail,
        created_by=current_user.username,
    )
    db.add(absence)
    db.flush()
    revision = bump_schedule_revision(db)
    _audit(db, "create", "absence_case", absence.id, current_user.username, {
        "teacher": professor.nom, "date": request.data.isoformat(), "periods": periods,
        **_absence_reason_payload(absence),
    })
    db.commit()
    return {"id": absence.id, "professor_id": professor.id, "teacher_name": professor.nom,
            "date": absence.data.isoformat(), "periods": periods, "status": absence.status,
            **_absence_reason_payload(absence),
            "revision": revision}


@router.post("/api/absence-cases/batch")
def create_absences_batch(
    request: AbsenceBatchCreateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("absence.create")),
):
    keys = [(item.professor_id, item.data) for item in request.items]
    if len(set(keys)) != len(keys):
        raise HTTPException(400, "同一教師及日期不可在同一批次重複")

    validated = []
    for item in request.items:
        existing = (db.query(AbsenceCase)
                    .filter_by(professor_id=item.professor_id, data=item.data)
                    .filter(AbsenceCase.status != "cancelled").first())
        if existing:
            can_manage_records = _ensure_absence_editable(current_user, existing)
            confirmed = (db.query(ScheduleAdjustment)
                         .filter_by(absence_case_id=existing.id, status="confirmed").count())
            if confirmed and not can_manage_records:
                raise HTTPException(409, "已有確認的調課，請由記錄管理員追加缺席節次")
        professor, periods = _validate_absence_request(db, item, allow_existing=True)
        existing_periods = set(json.loads(existing.periods_json or "[]")) if existing else set()
        added_periods = sorted(set(periods) - existing_periods)
        if (not existing or added_periods) and professor.id not in _professors_with_lessons(
            db, item.data, added_periods or periods
        ):
            raise HTTPException(400, f"{professor.nom} 在 {item.data.isoformat()} 所選節次沒有需要處理的課堂")
        validated.append((item, professor, sorted(existing_periods | set(periods)), added_periods, existing))

    selected_cases: list[AbsenceCase] = []
    created_ids: list[int] = []
    updated_ids: list[int] = []
    for item, professor, periods, added_periods, existing in validated:
        if existing:
            periods_changed = json.loads(existing.periods_json or "[]") != periods
            reason_changed = not existing.reason_type
            if periods_changed or reason_changed:
                existing.periods_json = json.dumps(periods)
                if reason_changed:
                    existing.reason_type = item.reason_type
                    existing.reason_detail = item.reason_detail
                if periods_changed:
                    existing.status = "open"
                updated_ids.append(existing.id)
                _audit(db, "update", "absence_case", existing.id, current_user.username, {
                    "teacher": professor.nom, "date": item.data.isoformat(),
                    "periods": periods, "added_periods": added_periods,
                    **_absence_reason_payload(existing),
                })
            selected_cases.append(existing)
            continue
        absence = AbsenceCase(
            professor_id=professor.id,
            data=item.data,
            periods_json=json.dumps(periods),
            reason_type=item.reason_type,
            reason_detail=item.reason_detail,
            created_by=current_user.username,
        )
        db.add(absence)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "缺席紀錄剛被其他人更新，請重新提交")
        selected_cases.append(absence)
        created_ids.append(absence.id)
        _audit(db, "create", "absence_case", absence.id, current_user.username, {
            "teacher": professor.nom, "date": item.data.isoformat(), "periods": periods,
            **_absence_reason_payload(absence),
        })
    if created_ids or updated_ids:
        bump_schedule_revision(db)
        db.commit()

    analyses = [
        {"date": target_date.isoformat(), **_analyze_current(db, _active_absences_for_date(db, target_date))}
        for target_date in sorted({item.data for item in request.items})
    ]
    return {
        **analyses[0],
        "analyses": analyses,
        "batch_absence_case_ids": [absence.id for absence in selected_cases],
        "created_absence_case_ids": created_ids,
        "updated_absence_case_ids": updated_ids,
    }


@router.post("/api/absence-cases/cancel-batch")
def cancel_absences_batch(
    request: AbsenceBatchCancelRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_any_permission("absence.create", "records.manage")),
):
    absence_ids = list(dict.fromkeys(request.absence_case_ids))
    absences = [db.get(AbsenceCase, absence_id) for absence_id in absence_ids]
    if any(absence is None or absence.status == "cancelled" for absence in absences):
        raise HTTPException(404, "找不到有效的缺席紀錄")
    for absence in absences:
        _ensure_absence_editable(current_user, absence)
    locked = (db.query(ScheduleAdjustment)
              .filter(ScheduleAdjustment.absence_case_id.in_(absence_ids),
                      ScheduleAdjustment.status == "confirmed").count())
    if locked:
        raise HTTPException(409, "已有鎖定的調課，請先撤銷調課")
    for absence in absences:
        absence.status = "cancelled"
        _audit(db, "cancel", "absence_case", absence.id, current_user.username)
    revision = bump_schedule_revision(db)
    db.commit()
    return {"success": True, "revision": revision}


@router.put("/api/absence-cases/{absence_id}")
def update_absence(
    absence_id: int,
    request: AbsenceCreateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_any_permission("absence.create", "records.manage")),
):
    absence = db.get(AbsenceCase, absence_id)
    if not absence:
        raise HTTPException(404, "找不到缺席紀錄")
    can_manage_records = _ensure_absence_editable(current_user, absence)
    professor, periods = _validate_absence_request(db, request, absence.id)
    identity_changed = absence.professor_id != professor.id or absence.data != request.data
    existing_periods = set(json.loads(absence.periods_json or "[]"))
    periods_changed = sorted(existing_periods) != periods
    schedule_changed = identity_changed or periods_changed
    confirmed = db.query(ScheduleAdjustment).filter_by(
        absence_case_id=absence.id, status="confirmed"
    ).count()
    if identity_changed and confirmed:
        raise HTTPException(409, "已有確認的調課，不能更改缺席老師或日期")
    if schedule_changed and confirmed and not can_manage_records:
        raise HTTPException(409, "已有確認的調課，請由記錄管理員修改缺席節次")
    if periods_changed and confirmed:
        protected_periods = {
            leg.from_period
            for leg in (
                db.query(ScheduleAdjustmentLeg)
                .join(ScheduleAdjustment, ScheduleAdjustmentLeg.adjustment_id == ScheduleAdjustment.id)
                .filter(
                    ScheduleAdjustment.absence_case_id == absence.id,
                    ScheduleAdjustment.status == "confirmed",
                    ScheduleAdjustmentLeg.from_date == absence.data,
                )
                .all()
            )
            if leg.replaced_teacher_id == absence.professor_id
            or absence.professor_id in json.loads(leg.teachers_json or "[]")
        }
        if (existing_periods - set(periods)) & protected_periods:
            raise HTTPException(409, "已有確認安排的缺席節次不可移除，請先撤銷相關安排")
    removed_ids = []
    if schedule_changed:
        if not confirmed:
            adjustments = db.query(ScheduleAdjustment).filter_by(absence_case_id=absence.id).all()
            removed_ids = [row.id for row in adjustments]
            for adjustment in adjustments:
                _delete_adjustment_rows(db, adjustment)
        absence.professor_id = professor.id
        absence.data = request.data
        absence.periods_json = json.dumps(periods)
    absence.reason_type = request.reason_type
    absence.reason_detail = request.reason_detail
    db.flush()
    absence.status = "open" if _analyze_current(db, [absence])["tasks"] else "resolved"
    revision = bump_schedule_revision(db) if schedule_changed else get_schedule_revision(db)
    _audit(db, "update", "absence_case", absence.id, current_user.username, {
        "teacher": professor.nom, "date": request.data.isoformat(), "periods": periods,
        "schedule_changed": schedule_changed, "removed_adjustments": removed_ids,
        **_absence_reason_payload(absence),
    })
    db.commit()
    return {"success": True, **_absence_reason_payload(absence), "revision": revision}


@router.delete("/api/absence-cases/{absence_id}/purge")
def purge_absence(
    absence_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("records.manage")),
    _records_user=Depends(require_permission("records.view")),
):
    absence = db.get(AbsenceCase, absence_id)
    if not absence:
        raise HTTPException(404, "找不到缺席紀錄")
    adjustments = db.query(ScheduleAdjustment).filter_by(absence_case_id=absence.id).all()
    removed_ids = [row.id for row in adjustments]
    for adjustment in adjustments:
        _delete_adjustment_rows(db, adjustment)
    detail = {"date": absence.data.isoformat(), "professor_id": absence.professor_id,
              "removed_adjustments": removed_ids}
    db.delete(absence)
    revision = bump_schedule_revision(db)
    _audit(db, "purge", "absence_case", absence_id, current_user.username, detail)
    db.commit()
    return {"success": True, "revision": revision}


@router.get("/api/absence-cases")
def list_absences(
    data: Optional[date] = None,
    db: Session = Depends(get_db),
    _current_user=Depends(require_permission("workbench.view")),
):
    query = db.query(AbsenceCase)
    if data:
        query = query.filter_by(data=data)
    rows = query.order_by(AbsenceCase.data.desc(), AbsenceCase.id.desc()).limit(100).all()
    names = {row.id: row.nom for row in db.query(Professor).all()}
    return [{
        "id": row.id, "professor_id": row.professor_id, "teacher_name": names.get(row.professor_id),
        "date": row.data.isoformat(), "periods": json.loads(row.periods_json), "status": row.status,
        "created_by": row.created_by, **_absence_reason_payload(row),
    } for row in rows]


@router.post("/api/absence-cases/{absence_id}/analyze")
def analyze(
    absence_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("absence.create")),
):
    absence = db.get(AbsenceCase, absence_id)
    if not absence or absence.status == "cancelled":
        raise HTTPException(404, "找不到有效的缺席紀錄")
    can_manage_records = _ensure_absence_editable(current_user, absence)
    if not can_manage_records and db.query(ScheduleAdjustment).filter_by(
        absence_case_id=absence.id, status="confirmed"
    ).count():
        raise HTTPException(409, "已有鎖定的調課，請先撤銷調課")
    return _analyze_current(db, _active_absences_for_date(db, absence.data))


@router.delete("/api/absence-cases/{absence_id}")
def cancel_absence(
    absence_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_any_permission("absence.create", "records.manage")),
):
    absence = db.get(AbsenceCase, absence_id)
    if not absence or absence.status == "cancelled":
        raise HTTPException(404, "找不到有效的缺席紀錄")
    _ensure_absence_editable(current_user, absence)
    locked = (db.query(ScheduleAdjustment).filter_by(absence_case_id=absence.id, status="confirmed").count())
    if locked:
        raise HTTPException(409, "請先撤銷這次缺席下已確認的調課")
    absence.status = "cancelled"
    revision = bump_schedule_revision(db)
    _audit(db, "cancel", "absence_case", absence.id, current_user.username)
    db.commit()
    return {"success": True, "revision": revision}


def _save_candidate(db: Session, candidate: dict, absence_case_id: int | None,
                    username: str, reason: str | None) -> ScheduleAdjustment:
    adjustment = ScheduleAdjustment(
        absence_case_id=absence_case_id,
        kind=candidate["kind"],
        status="confirmed",
        locked=True,
        reason=reason or candidate.get("reason"),
        created_by=username,
        confirmed_by=username,
    )
    db.add(adjustment)
    db.flush()
    for leg in candidate["legs"]:
        db.add(ScheduleAdjustmentLeg(
            adjustment_id=adjustment.id,
            lesson_id=int(leg["lesson_id"]),
            class_code=leg["class_code"],
            subject=leg["subject"],
            teachers_json=json.dumps([int(value) for value in leg["teachers"]]),
            from_date=date.fromisoformat(leg["from_date"]),
            from_period=int(leg["from_period"]),
            to_date=date.fromisoformat(leg["to_date"]),
            to_period=int(leg["to_period"]),
            replaced_teacher_id=leg.get("replaced_teacher_id"),
            replacement_teacher_id=leg.get("replacement_teacher_id"),
        ))
    return adjustment


def _manual_cover_candidates(
    db: Session,
    absence: AbsenceCase,
    target: dict,
    occurrences: list[dict] | None = None,
) -> list[dict]:
    """Return free teachers ranked by how clear the periods around the target are."""
    version = version_for_date(db, absence.data)
    if not version:
        return []
    occurrences = occurrences or effective_occurrences(db, absence.data, absence.data)
    absences = absence_keys(db, absence.data, absence.data)
    teacher_ids = professor_ids_for_version(db, version)
    teachers = {
        row.id: row.nom
        for row in db.query(Professor)
        .filter(Professor.id.in_(teacher_ids), Professor.actiu.is_(True)).all()
    }
    subjects_by_teacher: dict[int, set[str]] = {}
    for lesson in db.query(TimetableLesson).filter_by(version_id=version.id).all():
        subject = normalize_subject(lesson.subject)
        for teacher_id in json.loads(lesson.teachers_json or "[]"):
            subjects_by_teacher.setdefault(int(teacher_id), set()).add(subject)

    cover_counts = {
        int(teacher_id): int(count)
        for teacher_id, count in (
            db.query(ScheduleAdjustmentLeg.replacement_teacher_id, func.count(ScheduleAdjustmentLeg.id))
            .join(ScheduleAdjustment, ScheduleAdjustmentLeg.adjustment_id == ScheduleAdjustment.id)
            .filter(
                ScheduleAdjustment.status == "confirmed",
                ScheduleAdjustment.kind == "emergency_cover",
                ScheduleAdjustmentLeg.replacement_teacher_id.is_not(None),
            )
            .group_by(ScheduleAdjustmentLeg.replacement_teacher_id)
            .all()
        )
    }
    busy_by_teacher: dict[int, dict[int, list[dict]]] = {}
    for occurrence in occurrences:
        for teacher_id in occurrence["teachers"]:
            busy_by_teacher.setdefault(int(teacher_id), {}).setdefault(occurrence["period"], []).append(occurrence)

    target_period = int(target["period"])
    max_period = len(get_period_times(db, absence.data))
    adjacent_periods = [period for period in (target_period - 1, target_period + 1) if 1 <= period <= max_period]
    target_subject = normalize_subject(target["subject"])
    candidates = []
    for teacher_id, teacher_name in teachers.items():
        if teacher_id == absence.professor_id or teacher_id in target["teachers"]:
            continue
        if (teacher_id, absence.data, target_period) in absences:
            continue
        if busy_by_teacher.get(teacher_id, {}).get(target_period):
            continue
        adjacent_busy_count = sum(
            bool(busy_by_teacher.get(teacher_id, {}).get(period))
            or (teacher_id, absence.data, period) in absences
            for period in adjacent_periods
        )
        adjacent_teaching = adjacent_teaching_count(
            occurrences, teacher_id, absence.data, target_period
        )
        slots = []
        for period in range(1, max_period + 1):
            lessons = busy_by_teacher.get(teacher_id, {}).get(period, [])
            unavailable = (teacher_id, absence.data, period) in absences
            slots.append({
                "period": period,
                "state": "target" if period == target_period else "busy" if lessons or unavailable else "free",
                "lessons": [{
                    "class_code": lesson["class_code"],
                    "subject": lesson["subject"],
                    "source": lesson["source"],
                } for lesson in lessons],
            })
        candidates.append({
            "id": teacher_id,
            "name": teacher_name,
            "same_subject": target_subject in subjects_by_teacher.get(teacher_id, set()),
            "cover_count": cover_counts.get(teacher_id, 0),
            "adjacent_busy_count": adjacent_busy_count,
            "adjacent_teaching_count": adjacent_teaching,
            "adjacent_total": len(adjacent_periods),
            "slots": slots,
        })
    candidates.sort(key=lambda item: (
        item["adjacent_teaching_count"],
        item["adjacent_busy_count"],
        not item["same_subject"],
        item["cover_count"],
        item["name"],
    ))
    return candidates


def _manual_arrangements(db: Session) -> dict:
    professor_names = {row.id: row.nom for row in db.query(Professor).all()}
    open_dates = [
        row[0]
        for row in (
            db.query(AbsenceCase.data)
            .filter(AbsenceCase.status == "open")
            .distinct()
            .order_by(AbsenceCase.data)
            .all()
        )
    ]
    tasks = []
    for target_date in open_dates:
        active_absences = _active_absences_for_date(db, target_date)
        analysis = _analyze_current(db, active_absences)
        occurrences = effective_occurrences(db, target_date, target_date)
        occurrence_map = {row["occurrence_id"]: row for row in occurrences}
        unavailable = absence_keys(db, target_date, target_date)
        absences_by_id = {row.id: row for row in active_absences}
        for task in analysis["tasks"]:
            if task["status"] not in {"recommended", "unresolved"}:
                continue
            absence = absences_by_id.get(task["absence_case_id"])
            target = occurrence_map.get(task["target"]["occurrence_id"])
            if not absence or not target:
                continue
            tasks.append({
                **task,
                "absent_teacher_id": absence.professor_id,
                "absent_teacher_name": professor_names.get(absence.professor_id, str(absence.professor_id)),
                **_absence_reason_payload(absence),
                "co_teachers": [{
                    "id": teacher_id,
                    "name": professor_names.get(teacher_id, str(teacher_id)),
                } for teacher_id in target["teachers"]
                    if teacher_id != absence.professor_id
                    and (teacher_id, target_date, target["period"]) not in unavailable],
                "candidates": _manual_cover_candidates(db, absence, target, occurrences),
            })
    return {"revision": get_schedule_revision(db), "tasks": tasks}


@router.get("/api/manual-arrangements")
def list_manual_arrangements(
    db: Session = Depends(get_db),
    _current_user=Depends(require_permission("manual_arrangement.manage")),
    _workbench_user=Depends(require_permission("workbench.view")),
):
    return _manual_arrangements(db)


@router.post("/api/manual-arrangements/cover")
def confirm_manual_cover(
    request: ManualCoverRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("manual_arrangement.manage")),
    _workbench_user=Depends(require_permission("workbench.view")),
):
    if request.co_teacher_only == (request.replacement_teacher_id is not None):
        raise HTTPException(400, "請選擇原任老師單獨上課或一位代課老師")
    if request.expected_revision != get_schedule_revision(db):
        raise HTTPException(409, "課表已被其他人修改，請重新載入")
    absence = db.get(AbsenceCase, request.absence_case_id)
    if not absence or absence.status != "open":
        raise HTTPException(404, "找不到未處理的缺席紀錄")
    active_absences = _active_absences_for_date(db, absence.data)
    analysis = _analyze_current(db, active_absences)
    task = next((item for item in analysis["tasks"] if (
        item["absence_case_id"] == absence.id
        and item["target"]["occurrence_id"] == request.occurrence_id
        and item["status"] in {"recommended", "unresolved"}
    )), None)
    if not task:
        raise HTTPException(409, "這堂課的狀態已改變，請重新載入")
    occurrences = effective_occurrences(db, absence.data, absence.data)
    target = next((row for row in occurrences if row["occurrence_id"] == request.occurrence_id), None)
    if not target or target["lesson_id"] is None or absence.professor_id not in target["teachers"]:
        raise HTTPException(409, "這堂課的狀態已改變，請重新載入")

    leg = {
        "occurrence_id": target["occurrence_id"],
        "lesson_id": target["lesson_id"],
        "class_code": target["class_code"],
        "subject": target["subject"],
        "teachers": target["teachers"],
        "from_date": absence.data.isoformat(),
        "from_period": target["period"],
        "to_date": absence.data.isoformat(),
        "to_period": target["period"],
        "replaced_teacher_id": absence.professor_id,
    }
    if request.co_teacher_only:
        unavailable = absence_keys(db, absence.data, absence.data)
        co_teacher_ids = [
            teacher_id for teacher_id in target["teachers"]
            if teacher_id != absence.professor_id
            and (teacher_id, absence.data, target["period"]) not in unavailable
        ]
        if not co_teacher_ids:
            raise HTTPException(409, "目前沒有仍在場的共同任教老師")
        names = {row.id: row.nom for row in db.query(Professor).filter(Professor.id.in_(co_teacher_ids)).all()}
        co_teacher_names = "、".join(names.get(teacher_id, str(teacher_id)) for teacher_id in co_teacher_ids)
        kind = "co_teacher_solo"
        reason = request.reason or f"人工確認：由原任 {co_teacher_names} 繼續上課"
        audit_detail = {"co_teacher_ids": co_teacher_ids, "occurrence_id": request.occurrence_id}
    else:
        candidates = _manual_cover_candidates(db, absence, target, occurrences)
        replacement = next((row for row in candidates if row["id"] == request.replacement_teacher_id), None)
        if not replacement:
            raise HTTPException(409, "所選老師已不可代課，請重新選擇")
        leg.update({
            "replacement_teacher_id": replacement["id"],
            "replacement_teacher_name": replacement["name"],
        })
        kind = "emergency_cover"
        reason = request.reason or f"人工安排：{replacement['name']} 代課"
        audit_detail = {"replacement_teacher_id": replacement["id"], "occurrence_id": request.occurrence_id}
    adjustment = _save_candidate(
        db,
        {"kind": kind, "legs": [leg], "reason": reason},
        absence.id,
        current_user.username,
        reason,
    )
    db.flush()
    revision = bump_schedule_revision(db)
    remaining = _analyze_current(db, active_absences)
    pending_case_ids = {item["absence_case_id"] for item in remaining["tasks"]}
    for active_absence in active_absences:
        active_absence.status = "open" if active_absence.id in pending_case_ids else "resolved"
    _audit(db, "manual_cover_confirm", "schedule_adjustment", adjustment.id, current_user.username,
           audit_detail)
    db.commit()
    return {**_serialize_adjustment(db, adjustment), "revision": revision}


@router.post("/api/adjustments/confirm")
def confirm_adjustment(
    request: ConfirmRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("adjustment.confirm")),
):
    if request.expected_revision != get_schedule_revision(db):
        raise HTTPException(409, "課表已被其他人修改，請重新分析")
    absence = db.get(AbsenceCase, request.absence_case_id)
    if not absence or absence.status == "cancelled":
        raise HTTPException(404, "找不到有效的缺席紀錄")
    active_absences = _active_absences_for_date(db, absence.data)
    analysis = _analyze_current(db, active_absences)
    candidate = candidate_from_analysis(analysis, request.candidate_id, absence.id)
    if not candidate:
        raise HTTPException(409, "這個建議已失效，請重新分析")
    adjustment = _save_candidate(db, candidate, absence.id, current_user.username, request.reason)
    db.flush()
    revision = bump_schedule_revision(db)
    remaining = _analyze_current(db, active_absences)
    pending_case_ids = {task["absence_case_id"] for task in remaining["tasks"]}
    for active_absence in active_absences:
        active_absence.status = "open" if active_absence.id in pending_case_ids else "resolved"
    _audit(db, "confirm", "schedule_adjustment", adjustment.id, current_user.username,
           {"candidate_id": request.candidate_id, "kind": candidate["kind"]})
    db.commit()
    return {**_serialize_adjustment(db, adjustment), "revision": revision, "analysis": remaining}


@router.post("/api/adjustments/manual")
def manual_adjustment(
    request: ManualAdjustmentRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("manual_arrangement.manage")),
    _workbench_user=Depends(require_permission("workbench.view")),
):
    if request.expected_revision != get_schedule_revision(db):
        raise HTTPException(409, "課表已被其他人修改，請重新載入")
    start = min(min(leg.from_date, leg.to_date) for leg in request.legs)
    end = max(max(leg.from_date, leg.to_date) for leg in request.legs)
    occurrences = effective_occurrences(db, start, end)
    occurrence_map = {occ["occurrence_id"]: occ for occ in occurrences}
    legs = []
    for requested in request.legs:
        source = occurrence_map.get(requested.occurrence_id)
        if not source or source["date"] != requested.from_date:
            raise HTTPException(409, "來源課堂已改變，請重新載入")
        legs.append({
            "occurrence_id": source["occurrence_id"], "lesson_id": source["lesson_id"],
            "class_code": source["class_code"], "subject": source["subject"],
            "teachers": source["teachers"], "from_date": source["date"].isoformat(),
            "from_period": source["period"], "to_date": requested.to_date.isoformat(),
            "to_period": requested.to_period,
        })
    source_slots = {(leg["from_date"], int(leg["from_period"])) for leg in legs}
    destination_slots = {(leg["to_date"], int(leg["to_period"])) for leg in legs}
    if source_slots != destination_slots:
        raise HTTPException(400, "人工安排必須是 2 或 3 堂課的完整互調，不可只把課移到空格")
    closures = {row.data for row in db.query(SchoolClosure).all()}
    ok, detail = validate_move_legs(
        legs, occurrences, absence_keys(db, start, end), closures,
        now=hong_kong_now(), period_starts=_period_starts(db, start),
    )
    if not ok:
        raise HTTPException(409, detail)
    candidate = {"kind": "manual_swap" if len(legs) == 2 else "manual_three_cycle", "legs": legs,
                 "reason": request.reason}
    adjustment = _save_candidate(db, candidate, None, current_user.username, request.reason)
    revision = bump_schedule_revision(db)
    _audit(db, "manual_confirm", "schedule_adjustment", adjustment.id, current_user.username)
    db.commit()
    return {**_serialize_adjustment(db, adjustment), "revision": revision}


@router.get("/api/adjustments")
def list_adjustments(
    limit: int = 50,
    db: Session = Depends(get_db),
    _current_user=Depends(require_permission("records.view")),
):
    rows = db.query(ScheduleAdjustment).order_by(ScheduleAdjustment.id.desc()).limit(min(limit, 200)).all()
    return [_serialize_adjustment(db, row) for row in rows]


@router.put("/api/adjustments/{adjustment_id}")
def update_adjustment(
    adjustment_id: int,
    request: UpdateAdjustmentRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("records.manage")),
    _records_user=Depends(require_permission("records.view")),
):
    adjustment = db.get(ScheduleAdjustment, adjustment_id)
    if not adjustment:
        raise HTTPException(404, "找不到調課紀錄")
    adjustment.reason = request.reason.strip() if request.reason and request.reason.strip() else None
    _audit(db, "update", "schedule_adjustment", adjustment.id, current_user.username,
           {"reason": adjustment.reason})
    db.commit()
    return _serialize_adjustment(db, adjustment)


@router.delete("/api/adjustments/{adjustment_id}")
def delete_adjustment(
    adjustment_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("records.manage")),
    _records_user=Depends(require_permission("records.view")),
):
    adjustment = db.get(ScheduleAdjustment, adjustment_id)
    if not adjustment:
        raise HTTPException(404, "找不到調課紀錄")
    if adjustment.status == "confirmed":
        raise HTTPException(409, "已確認的調課必須使用撤銷，以保留歷史記錄")
    absence_id = adjustment.absence_case_id
    detail = {"kind": adjustment.kind, "status": adjustment.status, "absence_case_id": absence_id}
    _delete_adjustment_rows(db, adjustment)
    if absence_id:
        absence = db.get(AbsenceCase, absence_id)
        if absence and absence.status != "cancelled":
            absence.status = "open"
    revision = bump_schedule_revision(db)
    _audit(db, "delete", "schedule_adjustment", adjustment_id, current_user.username, detail)
    db.commit()
    return {"success": True, "revision": revision}


@router.get("/api/records")
def list_records(
    scope: str = Query("all", pattern="^(all|future|today|past)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=5, le=50),
    date_from: date | None = None,
    date_to: date | None = None,
    q: str | None = None,
    status: str | None = None,
    kind: str | None = None,
    db: Session = Depends(get_db),
    _current_user=Depends(require_permission("records.view")),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(400, "開始日期不可遲於結束日期")
    if status not in {None, "open", "completed"}:
        raise HTTPException(400, "無效的記錄狀態")
    if kind not in {None, "swap", "cover", "manual"}:
        raise HTTPException(400, "無效的調課類型")
    today = hong_kong_today()
    adjustments = (db.query(ScheduleAdjustment)
                   .filter(ScheduleAdjustment.status != "reverted")
                   .order_by(ScheduleAdjustment.id.desc()).all())
    by_absence: dict[int, list[ScheduleAdjustment]] = {}
    for adjustment in adjustments:
        if adjustment.absence_case_id:
            by_absence.setdefault(adjustment.absence_case_id, []).append(adjustment)

    names = {row.id: row.nom for row in db.query(Professor).all()}
    items = []
    for absence in db.query(AbsenceCase).filter(AbsenceCase.status != "cancelled").all():
        items.append({
            "id": f"absence-{absence.id}",
            "entity_id": absence.id,
            "record_type": "absence",
            "professor_id": absence.professor_id,
            "date": absence.data.isoformat(),
            "teacher_name": names.get(absence.professor_id),
            "periods": json.loads(absence.periods_json or "[]"),
            **_absence_reason_payload(absence),
            "status": absence.status,
            "needs_review": any(row.needs_review for row in by_absence.get(absence.id, [])),
            "created_by": absence.created_by,
            "adjustments": [_serialize_adjustment(db, row) for row in by_absence.get(absence.id, [])],
            "_sort_id": absence.id,
        })

    for adjustment in (row for row in adjustments if row.absence_case_id is None):
        serialized = _serialize_adjustment(db, adjustment)
        leg_dates = [date.fromisoformat(leg["from_date"]) for leg in serialized["legs"]]
        if not leg_dates:
            continue
        items.append({
            "id": f"adjustment-{adjustment.id}",
            "entity_id": adjustment.id,
            "record_type": "manual_adjustment",
            "professor_id": None,
            "date": min(leg_dates).isoformat(),
            "teacher_name": None,
            "periods": sorted({leg["from_period"] for leg in serialized["legs"]}),
            "status": adjustment.status,
            "needs_review": bool(adjustment.needs_review),
            "created_by": adjustment.created_by,
            "adjustments": [serialized],
            "_sort_id": adjustment.id,
        })

    def in_scope(item):
        item_date = date.fromisoformat(item["date"])
        return (scope == "all"
                or (scope == "future" and item_date > today)
                or (scope == "today" and item_date == today)
                or (scope == "past" and item_date < today))

    # ponytail: in-memory filters fit the current single-school volume; move them to SQL if records become large.
    items = [item for item in items if in_scope(item)]
    if date_from:
        items = [item for item in items if date.fromisoformat(item["date"]) >= date_from]
    if date_to:
        items = [item for item in items if date.fromisoformat(item["date"]) <= date_to]
    if status == "open":
        items = [item for item in items if item["status"] == "open"]
    elif status == "completed":
        items = [item for item in items if item["status"] in {"resolved", "confirmed"}]
    if kind:
        allowed_kinds = {
            "swap": {"direct_swap", "three_cycle"},
            "cover": {"emergency_cover", "co_teacher_solo"},
            "manual": {"manual_swap", "manual_three_cycle"},
        }[kind]
        items = [item for item in items
                 if any(adjustment["kind"] in allowed_kinds for adjustment in item["adjustments"])]
    if q and (term := q.strip().casefold()):
        items = [item for item in items
                 if term in json.dumps(item, ensure_ascii=False).casefold()]
    items.sort(key=lambda item: (item["date"], item["_sort_id"]), reverse=scope != "future")
    total = len(items)
    start = (page - 1) * page_size
    page_items = items[start:start + page_size]
    for item in page_items:
        item.pop("_sort_id", None)
    return {
        "scope": scope,
        "today": today.isoformat(),
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": max(1, math.ceil(total / page_size)),
        "items": page_items,
    }


@router.get("/api/teacher-leaves")
def list_teacher_leaves(
    db: Session = Depends(get_db),
    _current_user=Depends(require_admin),
):
    professor_ids = {row.nom: row.id for row in db.query(Professor).all()}
    rows = (db.query(ProfessorBaixa)
            .order_by(ProfessorBaixa.data_inici.desc(), ProfessorBaixa.id.desc()).all())
    return [_serialize_leave(row, professor_ids) for row in rows]


@router.post("/api/teacher-leaves")
def create_teacher_leave(
    request: TeacherLeaveRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    professor = db.get(Professor, request.professor_id)
    if not professor:
        raise HTTPException(404, "找不到教師")
    if request.start_date > request.end_date:
        raise HTTPException(400, "結束日期不可早於開始日期")
    if request.leave_type not in {"sick", "maternity", "other"}:
        raise HTTPException(400, "不支援的長期缺席類型")
    overlap = (db.query(ProfessorBaixa)
               .filter(ProfessorBaixa.professor == professor.nom,
                       ProfessorBaixa.data_inici <= request.end_date,
                       ProfessorBaixa.data_final >= request.start_date).first())
    if overlap:
        raise HTTPException(409, "該教師已有重疊的長期缺席紀錄")
    leave = ProfessorBaixa(
        professor=professor.nom,
        data_inici=request.start_date,
        data_final=request.end_date,
        motiu=request.leave_type,
    )
    db.add(leave)
    db.flush()
    revision = bump_schedule_revision(db)
    _audit(db, "create", "teacher_leave", leave.id, current_user.username,
           {"teacher": professor.nom, "start_date": request.start_date.isoformat(),
            "end_date": request.end_date.isoformat(), "leave_type": request.leave_type})
    db.commit()
    professor_ids = {professor.nom: professor.id}
    return {**_serialize_leave(leave, professor_ids), "revision": revision}


@router.put("/api/teacher-leaves/{leave_id}")
def update_teacher_leave(
    leave_id: int,
    request: TeacherLeaveRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    leave = db.get(ProfessorBaixa, leave_id)
    professor = db.get(Professor, request.professor_id)
    if not leave or not professor:
        raise HTTPException(404, "找不到長期缺席紀錄或教師")
    if request.start_date > request.end_date:
        raise HTTPException(400, "結束日期不可早於開始日期")
    if request.leave_type not in {"sick", "maternity", "other"}:
        raise HTTPException(400, "不支援的長期缺席類型")
    overlap = (db.query(ProfessorBaixa)
               .filter(ProfessorBaixa.id != leave_id,
                       ProfessorBaixa.professor == professor.nom,
                       ProfessorBaixa.data_inici <= request.end_date,
                       ProfessorBaixa.data_final >= request.start_date).first())
    if overlap:
        raise HTTPException(409, "該教師已有重疊的長期缺席紀錄")
    leave.professor = professor.nom
    leave.data_inici = request.start_date
    leave.data_final = request.end_date
    leave.motiu = request.leave_type
    revision = bump_schedule_revision(db)
    _audit(db, "update", "teacher_leave", leave.id, current_user.username)
    db.commit()
    return {**_serialize_leave(leave, {professor.nom: professor.id}), "revision": revision}


@router.delete("/api/teacher-leaves/{leave_id}")
def delete_teacher_leave(
    leave_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    leave = db.get(ProfessorBaixa, leave_id)
    if not leave:
        raise HTTPException(404, "找不到長期缺席紀錄")
    _audit(db, "delete", "teacher_leave", leave.id, current_user.username,
           {"teacher": leave.professor, "start_date": leave.data_inici.isoformat(),
            "end_date": leave.data_final.isoformat(), "leave_type": leave.motiu})
    db.delete(leave)
    revision = bump_schedule_revision(db)
    db.commit()
    return {"success": True, "revision": revision}


@router.post("/api/adjustments/{adjustment_id}/revert")
def revert_adjustment(
    adjustment_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("records.manage")),
    _records_user=Depends(require_permission("records.view")),
):
    adjustment = db.get(ScheduleAdjustment, adjustment_id)
    if not adjustment:
        raise HTTPException(404, "找不到調課紀錄")
    if adjustment.status != "confirmed":
        raise HTTPException(409, "這項調動已經撤銷")
    legs = db.query(ScheduleAdjustmentLeg).filter_by(adjustment_id=adjustment.id).all()
    if _adjustment_execution_state(db, legs) != "pending":
        raise HTTPException(409, "調課涉及的節次已開始或已過去，不能撤銷")
    if _has_confirmed_downstream_adjustment(db, adjustment, legs):
        raise HTTPException(409, "此調課已有後續安排，請先撤銷最新安排")
    adjustment.status = "reverted"
    adjustment.locked = False
    adjustment.reverted_by = current_user.username
    adjustment.reverted_at = utc_now()
    if adjustment.absence_case_id:
        absence = db.get(AbsenceCase, adjustment.absence_case_id)
        if absence and absence.status != "cancelled":
            absence.status = "open"
    revision = bump_schedule_revision(db)
    _audit(db, "revert", "schedule_adjustment", adjustment.id, current_user.username)
    db.commit()
    return {"success": True, "revision": revision}


@router.get("/api/effective-timetable")
def get_effective_timetable(
    data: date,
    professor_id: Optional[int] = None,
    class_code: Optional[str] = None,
    db: Session = Depends(get_db),
    _current_user=Depends(require_permission("workbench.view")),
):
    professor_names = {row.id: row.nom for row in db.query(Professor).all()}
    version = version_for_date(db, data)
    rows = effective_occurrences(db, data, data)
    if professor_id:
        rows = [row for row in rows if professor_id in row["teachers"]]
    if class_code:
        rows = [row for row in rows if row["class_code"] == class_code]
    rows.sort(key=lambda row: (row["period"], row["class_code"], row["subject"]))
    touching_ids = {
        row[0] for row in (
            db.query(ScheduleAdjustment.id)
            .join(ScheduleAdjustmentLeg, ScheduleAdjustmentLeg.adjustment_id == ScheduleAdjustment.id)
            .filter(
                ScheduleAdjustment.status == "confirmed",
                or_(ScheduleAdjustmentLeg.from_date == data, ScheduleAdjustmentLeg.to_date == data),
            )
            .distinct()
            .all()
        )
    }
    adjustment_ids = touching_ids | {row["adjustment_id"] for row in rows if row["adjustment_id"]}
    legs = (db.query(ScheduleAdjustmentLeg)
            .filter(ScheduleAdjustmentLeg.adjustment_id.in_(adjustment_ids)).all()
            if adjustment_ids else [])
    legs_by_destination = {
        (leg.adjustment_id, leg.lesson_id, leg.to_date, leg.to_period): leg
        for leg in legs
    }
    lessons = []
    for row in rows:
        leg = legs_by_destination.get((row["adjustment_id"], row["lesson_id"], data, row["period"]))
        lessons.append({
            "occurrence_id": row["occurrence_id"], "lesson_id": row["lesson_id"],
            "period": row["period"], "class_code": row["class_code"], "subject": row["subject"],
            "teacher_ids": row["teachers"],
            "teacher_names": [professor_names.get(value, str(value)) for value in row["teachers"]],
            "locked": row["locked"], "source": row["source"], "adjustment_id": row["adjustment_id"],
            "from_date": leg.from_date.isoformat() if leg else None,
            "from_period": leg.from_period if leg else None,
            "to_date": leg.to_date.isoformat() if leg else None,
            "to_period": leg.to_period if leg else None,
            "replacement_teacher_name": professor_names.get(leg.replacement_teacher_id) if leg and leg.replacement_teacher_id else None,
        })
    return {
        "date": data.isoformat(),
        "post_exam": bool(version and is_post_exam_version(version)),
        "effective_ranges": serialize_ranges(version_ranges(version)) if version else [],
        "period_count": len(get_period_times(db, data)),
        "revision": get_schedule_revision(db),
        "lessons": lessons,
        "adjustments": [
            _serialize_adjustment(db, adjustment)
            for adjustment in (
                db.query(ScheduleAdjustment)
                .filter(ScheduleAdjustment.id.in_(touching_ids))
                .order_by(ScheduleAdjustment.id)
                .all()
            )
        ] if touching_ids else [],
    }


@router.get("/api/calendar/closures")
def get_closures(
    year: Optional[int] = None,
    db: Session = Depends(get_db),
    _current_user=Depends(require_permission("workbench.view")),
):
    query = db.query(SchoolClosure)
    if year is not None:
        if not 1900 <= year <= 2100:
            raise HTTPException(400, "年份必須介乎 1900 至 2100")
        query = query.filter(SchoolClosure.data >= date(year, 1, 1), SchoolClosure.data <= date(year, 12, 31))
    return [{"date": row.data.isoformat(), "note": row.note} for row in query.order_by(SchoolClosure.data).all()]


@router.put("/api/calendar/closures")
def replace_closures(
    request: ClosureListRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    if not 1900 <= request.year <= 2100:
        raise HTTPException(400, "年份必須介乎 1900 至 2100")
    if any(item.data.year != request.year for item in request.closures):
        raise HTTPException(400, "假期日期必須位於所選年份內")
    start, end = date(request.year, 1, 1), date(request.year, 12, 31)
    db.query(SchoolClosure).filter(
        SchoolClosure.data >= start,
        SchoolClosure.data <= end,
    ).delete(synchronize_session=False)
    unique = {item.data: item for item in request.closures}
    for item in unique.values():
        db.add(SchoolClosure(data=item.data, note=item.note, created_by=current_user.username))
    revision = bump_schedule_revision(db)
    _audit(db, "replace", "school_closures", None, current_user.username,
           {"year": request.year, "dates": [value.isoformat() for value in sorted(unique)]})
    db.commit()
    return {"success": True, "revision": revision}
