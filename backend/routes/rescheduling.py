"""API for timetable import, absence analysis and confirmed lesson swaps."""
from datetime import date
from io import BytesIO
import json
import math
import uuid
import zipfile
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from auth_utils import get_current_user, require_admin
from dependencies import get_db
from models import (
    AbsenceCase,
    Configuracio,
    Curs,
    Professor,
    ProfessorBaixa,
    ScheduleAdjustment,
    ScheduleAdjustmentLeg,
    ScheduleAudit,
    SchoolClosure,
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
    analyze_absences,
    apply_import_resolutions,
    build_import_preview,
    bump_schedule_revision,
    candidate_from_analysis,
    effective_occurrences,
    get_max_cycle_lessons,
    get_schedule_revision,
    validate_move_legs,
    absence_keys,
    professor_ids_for_version,
    version_for_date,
)
from time_utils import hong_kong_today, utc_iso, utc_now


router = APIRouter(tags=["調課推薦"])
MAX_UPLOAD_BYTES = 12 * 1024 * 1024


class ActivateTimetableRequest(BaseModel):
    effective_from: date
    effective_to: date
    resolutions: dict[str, Literal["class", "teacher"]] = Field(default_factory=dict)
    special_subjects: list[str] = Field(default_factory=list)


class UpdateTimetableRequest(BaseModel):
    effective_from: date
    effective_to: date
    special_subjects: Optional[list[str]] = None


class SaveImportResolutionsRequest(BaseModel):
    resolutions: dict[str, Literal["class", "teacher"]] = Field(min_length=1)


class AbsenceCreateRequest(BaseModel):
    professor_id: int
    data: date
    periods: list[int] = Field(min_length=1)


class AbsenceBatchCreateRequest(BaseModel):
    items: list[AbsenceCreateRequest] = Field(min_length=1, max_length=3)


class AbsenceBatchCancelRequest(BaseModel):
    absence_case_ids: list[int] = Field(min_length=1)


class ConfirmRequest(BaseModel):
    absence_case_id: int
    candidate_id: str
    expected_revision: int
    reason: Optional[str] = None


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
    course_id: Optional[int] = None


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


def _serialize_adjustment(db: Session, adjustment: ScheduleAdjustment) -> dict:
    professor_names = {row.id: row.nom for row in db.query(Professor).all()}
    legs = db.query(ScheduleAdjustmentLeg).filter_by(adjustment_id=adjustment.id).order_by(ScheduleAdjustmentLeg.id).all()
    return {
        "id": adjustment.id,
        "absence_case_id": adjustment.absence_case_id,
        "kind": adjustment.kind,
        "status": adjustment.status,
        "locked": adjustment.locked,
        "reason": adjustment.reason,
        "confirmed_by": adjustment.confirmed_by,
        "confirmed_at": utc_iso(adjustment.confirmed_at),
        "reverted_by": adjustment.reverted_by,
        "reverted_at": utc_iso(adjustment.reverted_at),
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
    absences, adjustment_ids = _records_in_range(db, version.effective_from, version.effective_to)
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
    return query.first()


def _version_record_dates(db: Session, version: TimetableVersion) -> set[date]:
    dates = {row[0] for row in db.query(AbsenceCase.data)
             .filter(AbsenceCase.data >= version.effective_from).all()
             if version.effective_to is None or row[0] <= version.effective_to}
    lesson_ids = {row[0] for row in db.query(TimetableLesson.id).filter_by(version_id=version.id).all()}
    for leg in db.query(ScheduleAdjustmentLeg).all():
        if leg.lesson_id in lesson_ids:
            dates.add(leg.from_date)
        for value in (leg.from_date, leg.to_date):
            if value >= version.effective_from and (version.effective_to is None or value <= version.effective_to):
                dates.add(value)
    return dates


def _mark_latest_version_active(db: Session) -> None:
    latest = (db.query(TimetableVersion)
              .order_by(TimetableVersion.effective_from.desc(), TimetableVersion.id.desc()).first())
    for row in db.query(TimetableVersion).all():
        row.active = bool(latest and row.id == latest.id)


@router.get("/api/timetables")
def list_timetable_versions(db: Session = Depends(get_db)):
    versions = (db.query(TimetableVersion)
                .order_by(TimetableVersion.effective_from.desc(), TimetableVersion.id.desc()).all())
    current = version_for_date(db, hong_kong_today())
    rows = []
    for version in versions:
        absences, adjustments = _version_usage(db, version)
        lessons = db.query(TimetableLesson).filter_by(version_id=version.id).all()
        rows.append({
            "id": version.id,
            "effective_from": version.effective_from.isoformat(),
            "effective_to": version.effective_to.isoformat() if version.effective_to else None,
            "class_filename": version.class_filename,
            "teacher_filename": version.teacher_filename,
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
    current_user=Depends(require_admin),
):
    version = db.get(TimetableVersion, version_id)
    if not version:
        raise HTTPException(404, "找不到課表版本")
    if request.effective_from > request.effective_to:
        raise HTTPException(400, "結束日期不可早於開始日期")
    lessons = db.query(TimetableLesson).filter_by(version_id=version.id).all()
    current_specials = {lesson.subject for lesson in lessons if lesson.special}
    requested_specials = set(request.special_subjects) if request.special_subjects is not None else current_specials
    available_subjects = {lesson.subject for lesson in lessons}
    if not requested_specials.issubset(available_subjects):
        raise HTTPException(400, "包含課表中不存在的特殊課程")
    dates_changed = (request.effective_from != version.effective_from
                     or request.effective_to != version.effective_to)
    specials_changed = requested_specials != current_specials
    if not dates_changed and not specials_changed:
        return {"success": True, "revision": get_schedule_revision(db)}
    if dates_changed and _overlapping_version(db, request.effective_from, request.effective_to, version.id):
        raise HTTPException(409, "課表適用日期與另一個版本重疊")
    if dates_changed:
        record_dates = _version_record_dates(db, version)
        if any(value < request.effective_from or value > request.effective_to for value in record_dates):
            raise HTTPException(409, "新日期範圍未能包含此版本的全部缺席或調課記錄")
    old_range = {"effective_from": version.effective_from.isoformat(),
                 "effective_to": version.effective_to.isoformat() if version.effective_to else None}
    version.effective_from = request.effective_from
    version.effective_to = request.effective_to
    for lesson in lessons:
        lesson.special = lesson.subject in requested_specials
    _mark_latest_version_active(db)
    revision = bump_schedule_revision(db)
    _audit(db, "update", "timetable_version", version.id, current_user.username,
           {"old": old_range, "effective_from": request.effective_from.isoformat(),
            "effective_to": request.effective_to.isoformat(),
            "old_special_subjects": sorted(current_specials),
            "special_subjects": sorted(requested_specials)})
    db.commit()
    return {"success": True, "revision": revision}


@router.delete("/api/timetables/{version_id}")
def delete_timetable_version(
    version_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
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
            "effective_to": version.effective_to.isoformat() if version.effective_to else None})
    db.commit()
    return {"success": True, "revision": revision}


@router.post("/api/timetables/import/preview")
async def preview_import(
    class_workbook: UploadFile = File(...),
    teacher_workbook: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    if not class_workbook.filename.lower().endswith(".xls"):
        raise HTTPException(400, "班別時間表必須是 .xls")
    if not teacher_workbook.filename.lower().endswith(".xlsx"):
        raise HTTPException(400, "教師時間表必須是 .xlsx（請使用非值日版本）")
    class_content = await class_workbook.read(MAX_UPLOAD_BYTES + 1)
    teacher_content = await teacher_workbook.read(MAX_UPLOAD_BYTES + 1)
    if len(class_content) > MAX_UPLOAD_BYTES or len(teacher_content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "課表檔案不可超過 12 MB")
    try:
        payload = build_import_preview(class_content, teacher_content)
    except Exception as exc:
        raise HTTPException(400, f"無法讀取課表：{exc}") from exc
    preview_id = uuid.uuid4().hex
    db.add(TimetableImportPreview(
        id=preview_id,
        payload=json.dumps(payload, ensure_ascii=False),
        class_filename=class_workbook.filename,
        teacher_filename=teacher_workbook.filename,
        created_by=current_user.username,
    ))
    _audit(db, "preview_import", "timetable_preview", preview_id, current_user.username, payload["summary"])
    db.commit()
    return {"preview_id": preview_id, **payload["summary"], "warnings": payload["warnings"],
            "issues": payload["issues"],
            "subjects": sorted({lesson["subject"] for lesson in payload["lessons"]})}


@router.post("/api/timetables/import/{preview_id}/activate")
def activate_import(
    preview_id: str,
    request: ActivateTimetableRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    preview = db.get(TimetableImportPreview, preview_id)
    if not preview:
        raise HTTPException(404, "找不到匯入預覽，請重新選擇檔案")
    payload = json.loads(preview.payload)
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
    if request.effective_from > request.effective_to:
        raise HTTPException(400, "結束日期不可早於開始日期")
    if _overlapping_version(db, request.effective_from, request.effective_to):
        raise HTTPException(409, "課表適用日期與另一個版本重疊")
    if any(_records_in_range(db, request.effective_from, request.effective_to)):
        raise HTTPException(409, "新版本適用日期範圍已有缺席或調課記錄，不能覆蓋")
    version = TimetableVersion(
        effective_from=request.effective_from,
        effective_to=request.effective_to,
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
    db.delete(preview)
    _mark_latest_version_active(db)
    revision = bump_schedule_revision(db)
    _audit(db, "activate_import", "timetable_version", version.id, current_user.username,
           {**payload["summary"], "resolutions": resolutions,
            "special_subjects": sorted(special_subjects)})
    db.commit()
    return {"version_id": version.id, "revision": revision, **payload["summary"],
             "warnings": payload["warnings"], "issues": payload.get("issues", [])}


@router.delete("/api/timetables/import/{preview_id}")
def discard_import_preview(
    preview_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
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
    current_user=Depends(require_admin),
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
def current_timetable(data: Optional[date] = None, db: Session = Depends(get_db)):
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
        "class_filename": version.class_filename,
        "teacher_filename": version.teacher_filename,
        "lessons": db.query(TimetableLesson).filter_by(version_id=version.id).count(),
        "revision": get_schedule_revision(db),
    }


@router.get("/api/rescheduling/teachers")
def list_teachers(data: Optional[date] = None, db: Session = Depends(get_db)):
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
    course_id: int,
    db: Session = Depends(get_db),
    _current_user=Depends(require_admin),
):
    course = db.get(Curs, course_id)
    if not course:
        raise HTTPException(404, "找不到學年")
    if not course.data_fi:
        raise HTTPException(400, "請先在配置頁補上學年結束日期")
    start, end = course.data_inici, course.data_fi
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
        "course": {
            "id": course.id,
            "name": course.nom,
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
    _current_user=Depends(require_admin),
):
    entries = daily_export_data(db, data)
    if not entries:
        raise HTTPException(404, "所選日期沒有缺席記錄")
    content = build_daily_xlsx(entries, get_period_times(db))
    return StreamingResponse(
        BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="daily-substitution-{data.isoformat()}.xlsx"'},
    )


@router.get("/api/rescheduling/exports/daily.pdf")
def export_daily_pdf(
    data: date,
    db: Session = Depends(get_db),
    _current_user=Depends(require_admin),
):
    entries = daily_export_data(db, data)
    if not entries:
        raise HTTPException(404, "所選日期沒有缺席記錄")
    periods = get_period_times(db)
    if len(entries) == 1:
        content = build_daily_pdf(entries[0], periods)
        return StreamingResponse(
            BytesIO(content), media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="daily-substitution-{data.isoformat()}.pdf"'},
        )

    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for entry in entries:
            archive.writestr(
                f"teacher-{entry['teacher_id']}-{data.isoformat()}.pdf",
                build_daily_pdf(entry, periods),
            )
    output.seek(0)
    return StreamingResponse(
        output, media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="daily-substitution-{data.isoformat()}.zip"'},
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
    if any(period < 1 or period > 9 for period in periods):
        raise HTTPException(400, "節次必須介乎 1 至 9")
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


@router.post("/api/absence-cases")
def create_absence(
    request: AbsenceCreateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    professor, periods = _validate_absence_request(db, request)
    if professor.id not in _professors_with_lessons(db, request.data, periods):
        raise HTTPException(400, "所選節次沒有需要處理的課堂")
    absence = AbsenceCase(
        professor_id=professor.id,
        data=request.data,
        periods_json=json.dumps(periods),
        created_by=current_user.username,
    )
    db.add(absence)
    db.flush()
    revision = bump_schedule_revision(db)
    _audit(db, "create", "absence_case", absence.id, current_user.username,
           {"teacher": professor.nom, "date": request.data.isoformat(), "periods": periods})
    db.commit()
    return {"id": absence.id, "professor_id": professor.id, "teacher_name": professor.nom,
            "date": absence.data.isoformat(), "periods": periods, "status": absence.status,
            "revision": revision}


@router.post("/api/absence-cases/batch")
def create_absences_batch(
    request: AbsenceBatchCreateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    keys = [(item.professor_id, item.data) for item in request.items]
    if len(set(keys)) != len(keys):
        raise HTTPException(400, "同一教師及日期不可在同一批次重複")

    validated = []
    for item in request.items:
        professor, periods = _validate_absence_request(db, item, allow_existing=True)
        if professor.id not in _professors_with_lessons(db, item.data, periods):
            raise HTTPException(400, f"{professor.nom} 在 {item.data.isoformat()} 所選節次沒有需要處理的課堂")
        existing = (db.query(AbsenceCase)
                    .filter_by(professor_id=professor.id, data=item.data)
                    .filter(AbsenceCase.status != "cancelled").first())
        if existing and json.loads(existing.periods_json or "[]") != periods:
            confirmed = (db.query(ScheduleAdjustment)
                         .filter_by(absence_case_id=existing.id, status="confirmed").count())
            if confirmed:
                raise HTTPException(409, "已有確認的調課，請先撤銷後再修改缺席節次")
        validated.append((item, professor, periods, existing))

    selected_cases: list[AbsenceCase] = []
    created_ids: list[int] = []
    updated_ids: list[int] = []
    for item, professor, periods, existing in validated:
        if existing:
            if json.loads(existing.periods_json or "[]") != periods:
                existing.periods_json = json.dumps(periods)
                existing.status = "open"
                updated_ids.append(existing.id)
                _audit(db, "update", "absence_case", existing.id, current_user.username,
                       {"teacher": professor.nom, "date": item.data.isoformat(),
                        "periods": periods})
            selected_cases.append(existing)
            continue
        absence = AbsenceCase(
            professor_id=professor.id,
            data=item.data,
            periods_json=json.dumps(periods),
            created_by=current_user.username,
        )
        db.add(absence)
        db.flush()
        selected_cases.append(absence)
        created_ids.append(absence.id)
        _audit(db, "create", "absence_case", absence.id, current_user.username,
               {"teacher": professor.nom, "date": item.data.isoformat(), "periods": periods})
    if created_ids or updated_ids:
        bump_schedule_revision(db)
        db.commit()

    analyses = [
        {"date": target_date.isoformat(), **analyze_absences(db, _active_absences_for_date(db, target_date))}
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
    current_user=Depends(get_current_user),
):
    absence_ids = list(dict.fromkeys(request.absence_case_ids))
    absences = [db.get(AbsenceCase, absence_id) for absence_id in absence_ids]
    if any(absence is None or absence.status == "cancelled" for absence in absences):
        raise HTTPException(404, "找不到有效的缺席紀錄")
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
    current_user=Depends(require_admin),
):
    absence = db.get(AbsenceCase, absence_id)
    if not absence:
        raise HTTPException(404, "找不到缺席紀錄")
    professor, periods = _validate_absence_request(db, request, absence.id)
    adjustments = db.query(ScheduleAdjustment).filter_by(absence_case_id=absence.id).all()
    removed_ids = [row.id for row in adjustments]
    for adjustment in adjustments:
        _delete_adjustment_rows(db, adjustment)
    absence.professor_id = professor.id
    absence.data = request.data
    absence.periods_json = json.dumps(periods)
    absence.status = "open"
    revision = bump_schedule_revision(db)
    _audit(db, "update", "absence_case", absence.id, current_user.username,
           {"teacher": professor.nom, "date": request.data.isoformat(), "periods": periods,
            "removed_adjustments": removed_ids})
    db.commit()
    return {"success": True, "revision": revision}


@router.delete("/api/absence-cases/{absence_id}/purge")
def purge_absence(
    absence_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
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
def list_absences(data: Optional[date] = None, db: Session = Depends(get_db)):
    query = db.query(AbsenceCase)
    if data:
        query = query.filter_by(data=data)
    rows = query.order_by(AbsenceCase.data.desc(), AbsenceCase.id.desc()).limit(100).all()
    names = {row.id: row.nom for row in db.query(Professor).all()}
    return [{
        "id": row.id, "professor_id": row.professor_id, "teacher_name": names.get(row.professor_id),
        "date": row.data.isoformat(), "periods": json.loads(row.periods_json), "status": row.status,
        "created_by": row.created_by,
    } for row in rows]


@router.post("/api/absence-cases/{absence_id}/analyze")
def analyze(absence_id: int, db: Session = Depends(get_db)):
    absence = db.get(AbsenceCase, absence_id)
    if not absence or absence.status == "cancelled":
        raise HTTPException(404, "找不到有效的缺席紀錄")
    return analyze_absences(db, _active_absences_for_date(db, absence.data))


@router.delete("/api/absence-cases/{absence_id}")
def cancel_absence(
    absence_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    absence = db.get(AbsenceCase, absence_id)
    if not absence or absence.status == "cancelled":
        raise HTTPException(404, "找不到有效的缺席紀錄")
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


@router.post("/api/adjustments/confirm")
def confirm_adjustment(
    request: ConfirmRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if request.expected_revision != get_schedule_revision(db):
        raise HTTPException(409, "課表已被其他人修改，請重新分析")
    absence = db.get(AbsenceCase, request.absence_case_id)
    if not absence or absence.status == "cancelled":
        raise HTTPException(404, "找不到有效的缺席紀錄")
    active_absences = _active_absences_for_date(db, absence.data)
    analysis = analyze_absences(db, active_absences)
    candidate = candidate_from_analysis(analysis, request.candidate_id, absence.id)
    if not candidate:
        raise HTTPException(409, "這個建議已失效，請重新分析")
    adjustment = _save_candidate(db, candidate, absence.id, current_user.username, request.reason)
    db.flush()
    revision = bump_schedule_revision(db)
    remaining = analyze_absences(db, active_absences)
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
    current_user=Depends(require_admin),
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
    ok, detail = validate_move_legs(legs, occurrences, absence_keys(db, start, end), closures)
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
def list_adjustments(limit: int = 50, db: Session = Depends(get_db)):
    rows = db.query(ScheduleAdjustment).order_by(ScheduleAdjustment.id.desc()).limit(min(limit, 200)).all()
    return [_serialize_adjustment(db, row) for row in rows]


@router.put("/api/adjustments/{adjustment_id}")
def update_adjustment(
    adjustment_id: int,
    request: UpdateAdjustmentRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
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
    current_user=Depends(require_admin),
):
    adjustment = db.get(ScheduleAdjustment, adjustment_id)
    if not adjustment:
        raise HTTPException(404, "找不到調課紀錄")
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
    scope: str = Query("today", pattern="^(future|today|past)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=5, le=50),
    db: Session = Depends(get_db),
):
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
            "status": absence.status,
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
            "created_by": adjustment.created_by,
            "adjustments": [serialized],
            "_sort_id": adjustment.id,
        })

    def in_scope(item):
        item_date = date.fromisoformat(item["date"])
        return ((scope == "future" and item_date > today)
                or (scope == "today" and item_date == today)
                or (scope == "past" and item_date < today))

    items = [item for item in items if in_scope(item)]
    items.sort(key=lambda item: (item["date"], item["_sort_id"]), reverse=scope == "past")
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
    current_user=Depends(require_admin),
):
    adjustment = db.get(ScheduleAdjustment, adjustment_id)
    if not adjustment:
        raise HTTPException(404, "找不到調課紀錄")
    if adjustment.status != "confirmed":
        raise HTTPException(409, "這項調動已經撤銷")
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
):
    professor_names = {row.id: row.nom for row in db.query(Professor).all()}
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
def get_closures(course_id: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(SchoolClosure)
    if course_id is not None:
        course = db.get(Curs, course_id)
        if not course or not course.data_fi:
            raise HTTPException(404, "找不到具完整日期範圍的學年")
        query = query.filter(SchoolClosure.data >= course.data_inici, SchoolClosure.data <= course.data_fi)
    return [{"date": row.data.isoformat(), "note": row.note} for row in query.order_by(SchoolClosure.data).all()]


@router.put("/api/calendar/closures")
def replace_closures(
    request: ClosureListRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    course = db.get(Curs, request.course_id) if request.course_id is not None else None
    if request.course_id is not None and (not course or not course.data_fi):
        raise HTTPException(404, "找不到具完整日期範圍的學年")
    if course:
        if any(not course.data_inici <= item.data <= course.data_fi for item in request.closures):
            raise HTTPException(400, "假期日期必須位於所選學年範圍內")
        db.query(SchoolClosure).filter(
            SchoolClosure.data >= course.data_inici,
            SchoolClosure.data <= course.data_fi,
        ).delete(synchronize_session=False)
    else:
        db.query(SchoolClosure).delete()
    unique = {item.data: item for item in request.closures}
    for item in unique.values():
        db.add(SchoolClosure(data=item.data, note=item.note, created_by=current_user.username))
    revision = bump_schedule_revision(db)
    _audit(db, "replace", "school_closures", None, current_user.username,
           {"course_id": request.course_id, "dates": [value.isoformat() for value in sorted(unique)]})
    db.commit()
    return {"success": True, "revision": revision}
