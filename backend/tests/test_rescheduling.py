import json
import os
import sys
import unittest
from copy import deepcopy
from datetime import date
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import (  # noqa: E402
    AbsenceCase,
    Base,
    Curs,
    Professor,
    ProfessorBaixa,
    ScheduleAdjustment,
    ScheduleAdjustmentLeg,
    SchoolClosure,
    TimetableImportPreview,
    TimetableLesson,
    TimetableTeacherSlot,
    TimetableVersion,
)
from daily_exports import build_daily_pdf, build_daily_xlsx, daily_export_data, get_period_times, save_period_times, validate_period_times  # noqa: E402
from openpyxl import load_workbook  # noqa: E402
from repositories import CursRepository  # noqa: E402
from rescheduling_service import apply_import_resolutions, absence_keys, analyze_absence, build_import_preview, choose_global, effective_occurrences, version_for_date  # noqa: E402
from routes.rescheduling import (  # noqa: E402
    AbsenceBatchCreateRequest,
    AbsenceCreateRequest,
    ClosureInput,
    ClosureListRequest,
    ReschedulingConfigRequest,
    UpdateTimetableRequest,
    UpdateAdjustmentRequest,
    SaveImportResolutionsRequest,
    create_absences_batch,
    discard_import_preview,
    delete_adjustment,
    delete_timetable_version,
    get_effective_timetable,
    get_closures,
    list_records,
    list_timetable_versions,
    purge_absence,
    replace_closures,
    save_import_resolutions,
    update_absence,
    update_adjustment,
    update_rescheduling_config,
    update_timetable_version,
    teacher_statistics,
)


class ReschedulingTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()

    def tearDown(self):
        self.db.close()

    def test_academic_years_keep_explicit_summer_gap(self):
        first = CursRepository.create(
            self.db, "2025-2026", date(2025, 9, 1), date(2026, 6, 30),
        )
        second = CursRepository.create(
            self.db, "2026-2027", date(2026, 9, 1), date(2027, 6, 30),
        )

        self.assertEqual(first.data_fi, date(2026, 6, 30))
        self.assertIsNone(CursRepository.get_for_date(self.db, "2026-07-15"))
        self.assertEqual(CursRepository.get_for_date(self.db, "2026-09-01").id, second.id)
        with self.assertRaises(ValueError):
            CursRepository.create(
                self.db, "重疊", date(2026, 6, 1), date(2026, 8, 31),
            )

    def test_course_holiday_replace_keeps_other_years(self):
        first = CursRepository.create(
            self.db, "2025-2026", date(2025, 9, 1), date(2026, 6, 30),
        )
        second = CursRepository.create(
            self.db, "2026-2027", date(2026, 9, 1), date(2027, 6, 30),
        )
        self.db.add_all([
            SchoolClosure(data=date(2025, 12, 25)),
            SchoolClosure(data=date(2026, 12, 25)),
        ])
        self.db.commit()

        replace_closures(
            ClosureListRequest(course_id=first.id, closures=[
                ClosureInput(data=date(2026, 1, 1)),
                ClosureInput(data=date(2026, 1, 1)),
            ]),
            self.db,
            SimpleNamespace(username="admin"),
        )

        self.assertEqual(get_closures(first.id, self.db), [{"date": "2026-01-01", "note": None}])
        self.assertEqual(get_closures(second.id, self.db), [{"date": "2026-12-25", "note": None}])
        with self.assertRaises(HTTPException):
            replace_closures(
                ClosureListRequest(
                    course_id=first.id,
                    closures=[ClosureInput(data=date(2026, 7, 1))],
                ),
                self.db,
                SimpleNamespace(username="admin"),
            )

    def test_batch_absence_creates_independent_cases_atomically(self):
        teachers = [Professor(nom=f"{name}老師", actiu=True) for name in ("A", "B", "C")]
        version = TimetableVersion(
            effective_from=date(2026, 8, 10), effective_to=date(2026, 8, 31),
            class_filename="classes.xls", teacher_filename="teachers.xlsx", active=True,
        )
        self.db.add_all([*teachers, version])
        self.db.flush()
        self.db.add_all([
            TimetableLesson(version_id=version.id, weekday=0, period=1, class_code="1A", subject="中文", teachers_json=json.dumps([teachers[0].id])),
            TimetableLesson(version_id=version.id, weekday=0, period=2, class_code="2A", subject="英文", teachers_json=json.dumps([teachers[1].id])),
            TimetableLesson(version_id=version.id, weekday=1, period=3, class_code="3A", subject="數學", teachers_json=json.dumps([teachers[2].id])),
        ])
        self.db.commit()

        result = create_absences_batch(
            AbsenceBatchCreateRequest(
                items=[
                    AbsenceCreateRequest(professor_id=teachers[0].id, data=date(2026, 8, 10), periods=[1]),
                    AbsenceCreateRequest(professor_id=teachers[1].id, data=date(2026, 8, 10), periods=[2]),
                    AbsenceCreateRequest(professor_id=teachers[2].id, data=date(2026, 8, 11), periods=[3]),
                ],
            ),
            self.db,
            SimpleNamespace(username="admin"),
        )

        rows = self.db.query(AbsenceCase).order_by(AbsenceCase.id).all()
        self.assertEqual(len(rows), 3)
        self.assertEqual([json.loads(row.periods_json) for row in rows], [[1], [2], [3]])
        self.assertEqual(result["batch_absence_case_ids"], [row.id for row in rows])
        self.assertEqual([item["date"] for item in result["analyses"]], ["2026-08-10", "2026-08-11"])

        with self.assertRaises(HTTPException):
            create_absences_batch(
                AbsenceBatchCreateRequest(
                    items=[
                        AbsenceCreateRequest(professor_id=teachers[0].id, data=date(2026, 8, 10), periods=[1]),
                        AbsenceCreateRequest(professor_id=999999, data=date(2026, 8, 10), periods=[1]),
                    ],
                ),
                self.db,
                SimpleNamespace(username="admin"),
            )
        self.assertEqual(self.db.query(AbsenceCase).count(), 3)

    def test_batch_absence_reuses_case_with_latest_periods(self):
        teacher = Professor(nom="A老師", actiu=True)
        version = TimetableVersion(
            effective_from=date(2026, 8, 10), effective_to=date(2026, 8, 31),
            class_filename="classes.xls", teacher_filename="teachers.xlsx", active=True,
        )
        self.db.add_all([teacher, version])
        self.db.flush()
        self.db.add_all([
            TimetableLesson(
                version_id=version.id, weekday=0, period=period, class_code="1A",
                subject=subject, teachers_json=json.dumps([teacher.id]),
            )
            for period, subject in ((3, "中文"), (4, "英文"))
        ])
        existing = AbsenceCase(
            professor_id=teacher.id, data=date(2026, 8, 10), periods_json="[3]",
        )
        self.db.add(existing)
        self.db.commit()

        result = create_absences_batch(
            AbsenceBatchCreateRequest(
                items=[AbsenceCreateRequest(professor_id=teacher.id, data=date(2026, 8, 10), periods=[4])],
            ),
            self.db,
            SimpleNamespace(username="admin"),
        )

        self.assertEqual(json.loads(existing.periods_json), [4])
        self.assertEqual(result["updated_absence_case_ids"], [existing.id])
        self.assertEqual(result["tasks"][0]["target"]["period"], 4)

    @patch("routes.rescheduling.hong_kong_today", return_value=date(2026, 8, 10))
    def test_batch_absence_with_no_lesson_creates_no_record_or_export(self, _today):
        teacher = Professor(nom="A老師", actiu=True)
        version = TimetableVersion(
            effective_from=date(2026, 8, 10), effective_to=date(2026, 8, 31),
            class_filename="classes.xls", teacher_filename="teachers.xlsx", active=True,
        )
        self.db.add_all([teacher, version])
        self.db.flush()
        self.db.add(TimetableLesson(
            version_id=version.id, weekday=0, period=2, class_code="1A",
            subject="中文", teachers_json=json.dumps([teacher.id]),
        ))
        self.db.commit()

        with self.assertRaises(HTTPException):
            create_absences_batch(
                AbsenceBatchCreateRequest(
                    items=[AbsenceCreateRequest(professor_id=teacher.id, data=date(2026, 8, 10), periods=[1])],
                ),
                self.db,
                SimpleNamespace(username="admin"),
            )

        self.assertEqual(self.db.query(AbsenceCase).count(), 0)
        self.assertEqual(list_records(scope="today", page=1, page_size=20, db=self.db)["total"], 0)
        self.assertEqual(daily_export_data(self.db, date(2026, 8, 10)), [])

    def test_timetable_version_crud_preserves_linked_records(self):
        teacher = Professor(nom="A老師", actiu=True)
        old_version = TimetableVersion(
            effective_from=date(2026, 8, 10), effective_to=date(2026, 8, 16), class_filename="old.xls",
            teacher_filename="old.xlsx", active=False,
        )
        unused_version = TimetableVersion(
            effective_from=date(2026, 8, 17), effective_to=date(2026, 12, 31), class_filename="new.xls",
            teacher_filename="new.xlsx", active=True,
        )
        self.db.add_all([teacher, old_version, unused_version])
        self.db.flush()
        lesson = TimetableLesson(
            version_id=old_version.id, weekday=0, period=1, class_code="1A",
            subject="中文", teachers_json=json.dumps([teacher.id]),
        )
        absence = AbsenceCase(
            professor_id=teacher.id, data=date(2026, 8, 11), periods_json="[1]",
        )
        adjustment = ScheduleAdjustment(kind="direct_swap", status="reverted", locked=False)
        self.db.add_all([lesson, absence, adjustment])
        self.db.flush()
        self.db.add(ScheduleAdjustmentLeg(
            adjustment_id=adjustment.id, lesson_id=lesson.id, class_code="1A", subject="中文",
            teachers_json=json.dumps([teacher.id]), from_date=date(2026, 8, 11), from_period=1,
            to_date=date(2026, 8, 11), to_period=2,
        ))
        self.db.commit()

        rows = list_timetable_versions(self.db)
        locked = next(row for row in rows if row["id"] == old_version.id)
        self.assertTrue(locked["locked"])
        self.assertEqual((locked["absence_records"], locked["adjustment_records"]), (1, 1))

        user = SimpleNamespace(username="admin")
        update_timetable_version(
            unused_version.id,
            UpdateTimetableRequest(effective_from=date(2026, 8, 18), effective_to=date(2026, 12, 31)),
            self.db, user,
        )
        delete_timetable_version(unused_version.id, self.db, user)
        self.assertIsNone(self.db.get(TimetableVersion, unused_version.id))
        self.assertIsNone(version_for_date(self.db, date(2026, 8, 17)))
        with self.assertRaises(HTTPException) as blocked_delete:
            delete_timetable_version(old_version.id, self.db, user)
        self.assertEqual(blocked_delete.exception.status_code, 409)

    def test_existing_timetable_special_subjects_can_be_updated(self):
        version = TimetableVersion(
            effective_from=date(2026, 8, 10), effective_to=date(2026, 8, 31),
            class_filename="classes.xls", teacher_filename="teachers.xlsx", active=True,
        )
        self.db.add(version)
        self.db.flush()
        lessons = [
            TimetableLesson(
                version_id=version.id, weekday=0, period=index, class_code="1A",
                subject=subject, teachers_json="[]",
            )
            for index, subject in enumerate(("體育", "中文"), 1)
        ]
        self.db.add_all(lessons)
        self.db.commit()

        update_timetable_version(
            version.id,
            UpdateTimetableRequest(
                effective_from=version.effective_from, effective_to=version.effective_to,
                special_subjects=["體育"],
            ),
            self.db,
            SimpleNamespace(username="admin"),
        )

        self.assertTrue(lessons[0].special)
        self.assertFalse(lessons[1].special)
        row = list_timetable_versions(self.db)[0]
        self.assertEqual(row["subjects"], ["中文", "體育"])
        self.assertEqual(row["special_subjects"], ["體育"])

    def test_import_preview_can_be_discarded(self):
        preview = TimetableImportPreview(
            id="discard-me", payload="{}", class_filename="classes.xls",
            teacher_filename="teachers.xlsx", created_by="admin",
        )
        self.db.add(preview)
        self.db.commit()

        discard_import_preview("discard-me", self.db, SimpleNamespace(username="admin"))

        self.assertIsNone(self.db.get(TimetableImportPreview, "discard-me"))

    def test_test_records_can_be_updated_and_purged_transactionally(self):
        teacher = Professor(nom="A老師", actiu=True)
        version = TimetableVersion(
            effective_from=date(2026, 8, 10), effective_to=date(2026, 8, 31),
            class_filename="classes.xls", teacher_filename="teachers.xlsx", active=True,
        )
        self.db.add_all([teacher, version])
        self.db.flush()
        lesson = TimetableLesson(
            version_id=version.id, weekday=0, period=1, class_code="1A",
            subject="中文", teachers_json=json.dumps([teacher.id]),
        )
        absence = AbsenceCase(
            professor_id=teacher.id, data=date(2026, 8, 11), periods_json="[1]", status="resolved",
        )
        adjustment = ScheduleAdjustment(
            absence_case_id=None, kind="direct_swap", status="confirmed", locked=True,
        )
        self.db.add_all([lesson, absence, adjustment])
        self.db.flush()
        adjustment.absence_case_id = absence.id
        self.db.add(ScheduleAdjustmentLeg(
            adjustment_id=adjustment.id, lesson_id=lesson.id, class_code="1A", subject="中文",
            teachers_json=json.dumps([teacher.id]), from_date=date(2026, 8, 11), from_period=1,
            to_date=date(2026, 8, 11), to_period=2,
        ))
        self.db.commit()
        user = SimpleNamespace(username="admin")

        update_absence(
            absence.id,
            AbsenceCreateRequest(professor_id=teacher.id, data=date(2026, 8, 12), periods=[2, 3]),
            self.db, user,
        )
        self.assertIsNone(self.db.get(ScheduleAdjustment, adjustment.id))
        self.assertEqual(json.loads(absence.periods_json), [2, 3])

        replacement = ScheduleAdjustment(
            absence_case_id=absence.id, kind="direct_swap", status="confirmed", locked=True,
        )
        self.db.add(replacement)
        self.db.flush()
        self.db.add(ScheduleAdjustmentLeg(
            adjustment_id=replacement.id, lesson_id=lesson.id, class_code="1A", subject="中文",
            teachers_json=json.dumps([teacher.id]), from_date=date(2026, 8, 12), from_period=2,
            to_date=date(2026, 8, 12), to_period=3,
        ))
        self.db.commit()
        update_adjustment(replacement.id, UpdateAdjustmentRequest(reason="測試原因"), self.db, user)
        self.assertEqual(replacement.reason, "測試原因")
        delete_adjustment(replacement.id, self.db, user)
        self.assertEqual(absence.status, "open")
        purge_absence(absence.id, self.db, user)
        self.assertIsNone(self.db.get(AbsenceCase, absence.id))

    @patch("rescheduling_service.parse_class_workbook")
    @patch("rescheduling_service.parse_teacher_workbook")
    @patch("rescheduling_service.teacher_names_from_workbook")
    def test_import_preview_reports_exact_mismatch(self, names_parser, teacher_parser, class_parser):
        names_parser.return_value = ["A老師"]
        teacher_parser.return_value = ([{
            "teacher": "A老師", "weekday": 0, "period": 1,
            "class_code": "1B", "subject": "中文",
        }], ["A老師"])
        class_parser.return_value = ([{
            "weekday": 0, "period": 1, "class_code": "1A",
            "subject": "中文", "teachers": ["A老師"],
        }], [(505, 540)])

        result = build_import_preview(b"class", b"teacher")

        self.assertEqual(result["summary"]["blocked_lessons"], 1)
        self.assertEqual(result["issues"][0]["code"], "teacher_slot_mismatch")
        self.assertEqual(result["issues"][0]["teacher_workbook"], "1B 中文")
        resolution_id = result["issues"][0]["resolution_id"]

        class_result = apply_import_resolutions(deepcopy(result), {resolution_id: "class"})
        self.assertTrue(class_result["lessons"][0]["movable"])
        self.assertEqual(class_result["teacher_slots"][0]["class_code"], "1A")

        teacher_result = apply_import_resolutions(deepcopy(result), {resolution_id: "teacher"})
        self.assertEqual(teacher_result["lessons"][0]["teachers"], [])
        self.assertFalse(teacher_result["lessons"][0]["movable"])
        self.assertEqual(teacher_result["teacher_slots"][0]["class_code"], "1B")

    @patch("rescheduling_service.parse_class_workbook")
    @patch("rescheduling_service.parse_teacher_workbook")
    @patch("rescheduling_service.teacher_names_from_workbook")
    def test_import_preview_can_add_teacher_workbook_extra_as_co_teacher(
        self, names_parser, teacher_parser, class_parser,
    ):
        names_parser.return_value = ["A老師", "B老師"]
        teacher_parser.return_value = ([
            {"teacher": "A老師", "weekday": 3, "period": 2, "class_code": "3C", "subject": "中文"},
            {"teacher": "B老師", "weekday": 3, "period": 2, "class_code": "3C", "subject": "中文"},
        ], ["A老師", "B老師"])
        class_parser.return_value = ([{
            "weekday": 3, "period": 2, "class_code": "3C",
            "subject": "中文", "teachers": ["B老師"],
        }], [(540, 575)])

        result = build_import_preview(b"class", b"teacher")

        self.assertEqual(len(result["issues"]), 1)
        self.assertEqual(result["issues"][0]["code"], "teacher_extra_assignment")
        resolution_id = result["issues"][0]["resolution_id"]

        teacher_result = apply_import_resolutions(deepcopy(result), {resolution_id: "teacher"})
        self.assertEqual(teacher_result["lessons"][0]["teachers"], ["B老師", "A老師"])
        self.assertTrue(teacher_result["lessons"][0]["movable"])

        class_result = apply_import_resolutions(deepcopy(result), {resolution_id: "class"})
        self.assertEqual(class_result["lessons"][0]["teachers"], ["B老師"])
        self.assertEqual([slot["teacher"] for slot in class_result["teacher_slots"]], ["B老師"])

    def test_import_review_decisions_can_be_saved_partially(self):
        preview = TimetableImportPreview(
            id="preview-1",
            class_filename="classes.xls",
            teacher_filename="teachers.xlsx",
            payload=json.dumps({
                "issues": [
                    {"severity": "review", "resolution_id": "first"},
                    {"severity": "review", "resolution_id": "second"},
                ]
            }, ensure_ascii=False),
        )
        self.db.add(preview)
        self.db.commit()

        result = save_import_resolutions(
            preview.id,
            SaveImportResolutionsRequest(resolutions={"first": "teacher"}),
            self.db,
            SimpleNamespace(username="admin"),
        )

        self.assertEqual(result["saved_resolutions"], {"first": "teacher"})
        self.assertEqual((result["confirmed_count"], result["remaining_count"]), (1, 1))
        saved_payload = json.loads(self.db.get(TimetableImportPreview, preview.id).payload)
        self.assertEqual(saved_payload["saved_resolutions"], {"first": "teacher"})

    def test_confirmed_swap_changes_effective_timetable_without_changing_base(self):
        teacher_a = Professor(nom="A老師", actiu=True)
        teacher_b = Professor(nom="B老師", actiu=True)
        self.db.add_all([teacher_a, teacher_b])
        self.db.flush()
        version = TimetableVersion(
            effective_from=date(2026, 8, 10), class_filename="classes.xls",
            teacher_filename="teachers.xlsx", active=True,
        )
        self.db.add(version)
        self.db.flush()
        lesson_a = TimetableLesson(
            version_id=version.id, weekday=0, period=1, class_code="1A",
            subject="中文", teachers_json=json.dumps([teacher_a.id]),
        )
        lesson_b = TimetableLesson(
            version_id=version.id, weekday=0, period=4, class_code="1A",
            subject="英文", teachers_json=json.dumps([teacher_b.id]),
        )
        self.db.add_all([lesson_a, lesson_b])
        self.db.flush()
        adjustment = ScheduleAdjustment(kind="direct_swap", status="confirmed", locked=True)
        self.db.add(adjustment)
        self.db.flush()
        self.db.add_all([
            ScheduleAdjustmentLeg(
                adjustment_id=adjustment.id, lesson_id=lesson_a.id, class_code="1A",
                subject="中文", teachers_json=json.dumps([teacher_a.id]),
                from_date=date(2026, 8, 10), from_period=1,
                to_date=date(2026, 8, 10), to_period=4,
            ),
            ScheduleAdjustmentLeg(
                adjustment_id=adjustment.id, lesson_id=lesson_b.id, class_code="1A",
                subject="英文", teachers_json=json.dumps([teacher_b.id]),
                from_date=date(2026, 8, 10), from_period=4,
                to_date=date(2026, 8, 10), to_period=1,
            ),
        ])
        self.db.commit()

        effective = effective_occurrences(self.db, date(2026, 8, 10), date(2026, 8, 10))
        by_period = {row["period"]: row for row in effective}
        self.assertEqual(by_period[1]["teachers"], [teacher_b.id])
        self.assertEqual(by_period[4]["teachers"], [teacher_a.id])
        self.assertEqual(self.db.get(TimetableLesson, lesson_a.id).period, 1)
        self.assertTrue(by_period[1]["locked"])
        payload = get_effective_timetable(data=date(2026, 8, 10), db=self.db)
        movements = {(row["subject"], row["from_period"], row["to_period"]) for row in payload["lessons"]}
        self.assertEqual(movements, {("中文", 1, 4), ("英文", 4, 1)})

    def test_effective_timetable_uses_version_for_each_date(self):
        teacher = Professor(nom="A老師", actiu=True)
        self.db.add(teacher)
        self.db.flush()
        old_version = TimetableVersion(
            effective_from=date(2026, 8, 10), class_filename="old.xls",
            teacher_filename="old.xlsx", active=False,
        )
        new_version = TimetableVersion(
            effective_from=date(2026, 8, 17), class_filename="new.xls",
            teacher_filename="new.xlsx", active=True,
        )
        self.db.add_all([old_version, new_version])
        self.db.flush()
        self.db.add_all([
            TimetableLesson(
                version_id=old_version.id, weekday=0, period=1, class_code="1A",
                subject="舊課表", teachers_json=json.dumps([teacher.id]),
            ),
            TimetableLesson(
                version_id=new_version.id, weekday=0, period=1, class_code="1A",
                subject="新課表", teachers_json=json.dumps([teacher.id]),
            ),
        ])
        self.db.commit()

        rows = effective_occurrences(self.db, date(2026, 8, 10), date(2026, 8, 17))
        subjects = {(row["date"], row["subject"]) for row in rows}
        self.assertIn((date(2026, 8, 10), "舊課表"), subjects)
        self.assertIn((date(2026, 8, 17), "新課表"), subjects)
        self.assertNotIn((date(2026, 8, 10), "新課表"), subjects)

    def test_global_choice_does_not_reuse_same_teacher_slot(self):
        shared_leg = {
            "occurrence_id": "lesson-a", "lesson_id": 1, "class_code": "1A",
            "subject": "中文", "teachers": [1], "from_date": "2026-08-10",
            "from_period": 1, "to_date": "2026-08-10", "to_period": 4,
        }
        first = {"id": "first", "day_distance": 0, "moved_lessons": 2,
                 "legs": [shared_leg]}
        second = {"id": "second", "day_distance": 0, "moved_lessons": 2,
                  "legs": [{**shared_leg, "occurrence_id": "lesson-b"}]}
        chosen = choose_global([[first], [second]])
        self.assertEqual(len(chosen), 1)

    def test_analysis_prefers_same_day_direct_swap(self):
        teacher_a = Professor(nom="A老師", actiu=True)
        teacher_b = Professor(nom="B老師", actiu=True)
        self.db.add_all([teacher_a, teacher_b])
        self.db.flush()
        version = TimetableVersion(
            effective_from=date(2026, 8, 10), class_filename="classes.xls",
            teacher_filename="teachers.xlsx", active=True,
        )
        self.db.add(version)
        self.db.flush()
        self.db.add_all([
            TimetableLesson(
                version_id=version.id, weekday=0, period=1, class_code="1A",
                subject="中文", teachers_json=json.dumps([teacher_a.id]),
            ),
            TimetableLesson(
                version_id=version.id, weekday=0, period=4, class_code="1A",
                subject="英文", teachers_json=json.dumps([teacher_b.id]),
            ),
        ])
        absence = AbsenceCase(
            professor_id=teacher_a.id, data=date(2026, 8, 10),
            periods_json="[1]", status="open",
        )
        self.db.add(absence)
        self.db.commit()

        analysis = analyze_absence(self.db, absence)
        self.assertEqual(analysis["resolved_count"], 1)
        self.assertEqual(analysis["tasks"][0]["recommended"]["kind"], "direct_swap")
        self.assertEqual(analysis["tasks"][0]["recommended"]["day_distance"], 0)

    def test_analysis_deprioritizes_cross_day_special_lessons(self):
        teachers = [Professor(nom=f"{name}老師", actiu=True) for name in "ABC"]
        self.db.add_all(teachers)
        self.db.flush()
        version = TimetableVersion(
            effective_from=date(2026, 8, 10), class_filename="classes.xls",
            teacher_filename="teachers.xlsx", active=True,
        )
        self.db.add(version)
        self.db.flush()
        self.db.add_all([
            TimetableLesson(
                version_id=version.id, weekday=0, period=1, class_code="1A",
                subject="中文", teachers_json=json.dumps([teachers[0].id]),
            ),
            TimetableLesson(
                version_id=version.id, weekday=1, period=2, class_code="1A",
                subject="體育", teachers_json=json.dumps([teachers[1].id]), special=True,
            ),
            TimetableLesson(
                version_id=version.id, weekday=2, period=2, class_code="1A",
                subject="數學", teachers_json=json.dumps([teachers[2].id]),
            ),
        ])
        absence = AbsenceCase(
            professor_id=teachers[0].id, data=date(2026, 8, 10),
            periods_json="[1]", status="open",
        )
        self.db.add(absence)
        self.db.commit()

        candidate = analyze_absence(self.db, absence)["tasks"][0]["recommended"]

        self.assertEqual(candidate["completion_date"], "2026-08-12")
        self.assertEqual(candidate["special_cross_day_moves"], 0)

    def test_analysis_uses_three_lesson_cycle_when_direct_swaps_conflict(self):
        teachers = [Professor(nom=f"{name}老師", actiu=True) for name in "ABC"]
        self.db.add_all(teachers)
        self.db.flush()
        version = TimetableVersion(
            effective_from=date(2026, 8, 10), class_filename="classes.xls",
            teacher_filename="teachers.xlsx", active=True,
        )
        self.db.add(version)
        self.db.flush()
        rows = [
            (1, "1A", "中文", teachers[0]), (2, "1A", "英文", teachers[1]),
            (3, "1A", "數學", teachers[2]),
            # Block A<->B because B is busy at period 1; block A<->C because A is busy at period 3.
            (1, "2A", "英文", teachers[1]), (3, "2B", "中文", teachers[0]),
        ]
        for period, class_code, subject, teacher in rows:
            self.db.add(TimetableLesson(
                version_id=version.id, weekday=0, period=period, class_code=class_code,
                subject=subject, teachers_json=json.dumps([teacher.id]),
            ))
        absence = AbsenceCase(
            professor_id=teachers[0].id, data=date(2026, 8, 10), periods_json="[1]", status="open",
        )
        self.db.add(absence)
        self.db.commit()

        analysis = analyze_absence(self.db, absence)
        self.assertEqual(analysis["tasks"][0]["recommended"]["kind"], "three_cycle")
        self.assertEqual(len(analysis["tasks"][0]["recommended"]["legs"]), 3)

    def test_configured_cycle_limit_enables_four_lesson_recommendation(self):
        teachers = [Professor(nom=f"{name}老師", actiu=True) for name in "ABCD"]
        self.db.add_all(teachers)
        self.db.flush()
        version = TimetableVersion(
            effective_from=date(2026, 8, 10), class_filename="classes.xls",
            teacher_filename="teachers.xlsx", active=True,
        )
        self.db.add(version)
        self.db.flush()
        main_lessons = [
            (1, "中文", teachers[0]), (2, "英文", teachers[1]),
            (3, "數學", teachers[2]), (4, "科學", teachers[3]),
        ]
        blockers = [
            (1, "2A", teachers[1]), (1, "2B", teachers[2]),
            (3, "2C", teachers[0]), (4, "2D", teachers[0]), (4, "2E", teachers[1]),
        ]
        self.db.add_all([
            TimetableLesson(
                version_id=version.id, weekday=0, period=period, class_code="1A",
                subject=subject, teachers_json=json.dumps([teacher.id]),
            ) for period, subject, teacher in main_lessons
        ] + [
            TimetableLesson(
                version_id=version.id, weekday=0, period=period, class_code=class_code,
                subject="阻擋", teachers_json=json.dumps([teacher.id]),
            ) for period, class_code, teacher in blockers
        ])
        absence = AbsenceCase(
            professor_id=teachers[0].id, data=date(2026, 8, 10), periods_json="[1]", status="open",
        )
        self.db.add(absence)
        self.db.commit()

        self.assertEqual(analyze_absence(self.db, absence)["tasks"][0]["status"], "unresolved")
        saved = update_rescheduling_config(
            ReschedulingConfigRequest(max_cycle_lessons=4),
            self.db,
            SimpleNamespace(username="admin"),
        )
        candidate = analyze_absence(self.db, absence)["tasks"][0]["recommended"]

        self.assertEqual(saved["max_cycle_lessons"], 4)
        self.assertEqual(candidate["kind"], "three_cycle")
        self.assertEqual(len(candidate["legs"]), 4)

    def test_emergency_cover_is_same_subject_and_only_when_no_swap_exists(self):
        absent_teacher = Professor(nom="A老師", actiu=True)
        same_subject_teacher = Professor(nom="C老師", actiu=True)
        self.db.add_all([absent_teacher, same_subject_teacher])
        self.db.flush()
        version = TimetableVersion(
            effective_from=date(2026, 8, 10), class_filename="classes.xls",
            teacher_filename="teachers.xlsx", active=True,
        )
        self.db.add(version)
        self.db.flush()
        self.db.add_all([
            TimetableLesson(
                version_id=version.id, weekday=0, period=1, class_code="1A",
                subject="中文", teachers_json=json.dumps([absent_teacher.id]),
            ),
            TimetableLesson(
                version_id=version.id, weekday=0, period=2, class_code="2A",
                subject="中文", teachers_json=json.dumps([same_subject_teacher.id]),
            ),
        ])
        absence = AbsenceCase(
            professor_id=absent_teacher.id, data=date(2026, 8, 10), periods_json="[1]", status="open",
        )
        self.db.add(absence)
        self.db.commit()

        analysis = analyze_absence(self.db, absence)
        candidate = analysis["tasks"][0]["recommended"]
        self.assertEqual(candidate["kind"], "emergency_cover")
        self.assertEqual(candidate["legs"][0]["replacement_teacher_id"], same_subject_teacher.id)

    def test_common_planning_slot_blocks_emergency_cover(self):
        absent_teacher = Professor(nom="A老師", actiu=True)
        planning_teacher = Professor(nom="C老師", actiu=True)
        self.db.add_all([absent_teacher, planning_teacher])
        self.db.flush()
        version = TimetableVersion(
            effective_from=date(2026, 8, 10), class_filename="classes.xls",
            teacher_filename="teachers.xlsx", active=True,
        )
        self.db.add(version)
        self.db.flush()
        self.db.add_all([
            TimetableLesson(
                version_id=version.id, weekday=0, period=1, class_code="1A",
                subject="中文", teachers_json=json.dumps([absent_teacher.id]),
            ),
            TimetableLesson(
                version_id=version.id, weekday=0, period=2, class_code="2A",
                subject="中文", teachers_json=json.dumps([planning_teacher.id]),
            ),
            TimetableTeacherSlot(
                version_id=version.id, professor_id=planning_teacher.id, weekday=0,
                period=1, class_code="", subject="共同備課",
            ),
        ])
        absence = AbsenceCase(
            professor_id=absent_teacher.id, data=date(2026, 8, 10), periods_json="[1]", status="open",
        )
        self.db.add(absence)
        self.db.commit()

        analysis = analyze_absence(self.db, absence)

        self.assertEqual(analysis["tasks"][0]["status"], "unresolved")
        self.assertEqual(analysis["tasks"][0]["alternatives"], [])

    def test_long_term_leave_blocks_every_period_in_date_range(self):
        teacher = Professor(nom="A老師", actiu=True)
        self.db.add(teacher)
        self.db.flush()
        self.db.add(ProfessorBaixa(
            professor=teacher.nom,
            data_inici=date(2026, 8, 12),
            data_final=date(2026, 8, 14),
            motiu="maternity",
        ))
        self.db.commit()

        keys = absence_keys(self.db, date(2026, 8, 11), date(2026, 8, 15))

        self.assertNotIn((teacher.id, date(2026, 8, 11), 1), keys)
        self.assertIn((teacher.id, date(2026, 8, 12), 1), keys)
        self.assertIn((teacher.id, date(2026, 8, 14), 9), keys)
        self.assertNotIn((teacher.id, date(2026, 8, 15), 9), keys)

    @patch("routes.rescheduling.hong_kong_today", return_value=date(2026, 8, 11))
    def test_records_are_split_by_hong_kong_today_and_paginated(self, _today):
        teacher = Professor(nom="A老師", actiu=True)
        self.db.add(teacher)
        self.db.flush()
        cases = []
        for day in (date(2026, 8, 10), date(2026, 8, 11), date(2026, 8, 12), date(2026, 8, 13)):
            cases.append(AbsenceCase(
                professor_id=teacher.id, data=day, periods_json="[1]", status="open",
            ))
        self.db.add_all(cases)
        self.db.flush()
        self.db.add(AbsenceCase(
            professor_id=teacher.id, data=date(2026, 8, 12), periods_json="[2]", status="cancelled",
        ))
        self.db.add(ScheduleAdjustment(
            absence_case_id=cases[2].id, kind="direct_swap", status="reverted", locked=False,
        ))
        cases[3].status = "resolved"
        self.db.add(ScheduleAdjustment(
            absence_case_id=cases[3].id, kind="emergency_cover", status="confirmed", locked=True,
        ))
        self.db.commit()

        today = list_records(scope="today", page=1, page_size=20, db=self.db)
        future = list_records(scope="future", page=1, page_size=1, db=self.db)
        past = list_records(scope="past", page=1, page_size=20, db=self.db)
        filtered = list_records(
            scope="all", page=1, page_size=20, date_from=date(2026, 8, 11),
            date_to=date(2026, 8, 12), q="A老師", status="open", db=self.db,
        )
        covers = list_records(scope="all", page=1, page_size=20, status="completed", kind="cover", db=self.db)

        self.assertEqual([item["date"] for item in today["items"]], ["2026-08-11"])
        self.assertEqual(future["total"], 2)
        self.assertEqual(future["pages"], 2)
        self.assertEqual(future["items"][0]["date"], "2026-08-12")
        self.assertEqual(future["items"][0]["adjustments"], [])
        self.assertEqual([item["date"] for item in past["items"]], ["2026-08-10"])
        self.assertEqual([item["date"] for item in filtered["items"]], ["2026-08-12", "2026-08-11"])
        self.assertEqual([item["date"] for item in covers["items"]], ["2026-08-13"])

    def test_statistics_daily_exports_and_complete_cycle_payload(self):
        absent, swap_teacher, cover_teacher = [Professor(nom=name, actiu=True) for name in ("甲老師", "乙老師", "丙老師")]
        course = Curs(nom="2026-2027", data_inici=date(2026, 8, 1), data_fi=date(2027, 7, 31))
        version = TimetableVersion(
            effective_from=date(2026, 8, 1), effective_to=date(2027, 7, 31),
            class_filename="classes.xls", teacher_filename="teachers.xlsx", active=True,
        )
        self.db.add_all([absent, swap_teacher, cover_teacher, course, version])
        self.db.flush()
        first = TimetableLesson(
            version_id=version.id, weekday=0, period=1, class_code="1A", subject="中文",
            teachers_json=json.dumps([absent.id]),
        )
        second = TimetableLesson(
            version_id=version.id, weekday=0, period=2, class_code="1A", subject="英文",
            teachers_json=json.dumps([swap_teacher.id]),
        )
        absence = AbsenceCase(
            professor_id=absent.id, data=date(2026, 8, 10), periods_json="[1]", status="resolved",
        )
        self.db.add_all([first, second, absence])
        self.db.flush()
        swap = ScheduleAdjustment(absence_case_id=absence.id, kind="direct_swap", status="confirmed", locked=True)
        cover = ScheduleAdjustment(absence_case_id=absence.id, kind="emergency_cover", status="confirmed", locked=True)
        self.db.add_all([swap, cover])
        self.db.flush()
        self.db.add_all([
            ScheduleAdjustmentLeg(
                adjustment_id=swap.id, lesson_id=first.id, class_code="1A", subject="中文",
                teachers_json=json.dumps([absent.id]), from_date=date(2026, 8, 10), from_period=1,
                to_date=date(2026, 8, 10), to_period=2,
            ),
            ScheduleAdjustmentLeg(
                adjustment_id=swap.id, lesson_id=second.id, class_code="1A", subject="英文",
                teachers_json=json.dumps([swap_teacher.id]), from_date=date(2026, 8, 10), from_period=2,
                to_date=date(2026, 8, 10), to_period=1,
            ),
            ScheduleAdjustmentLeg(
                adjustment_id=cover.id, lesson_id=first.id, class_code="1A", subject="中文",
                teachers_json=json.dumps([absent.id]), from_date=date(2026, 9, 1), from_period=3,
                to_date=date(2026, 9, 1), to_period=3, replaced_teacher_id=absent.id,
                replacement_teacher_id=cover_teacher.id,
            ),
        ])
        self.db.commit()

        statistics = teacher_statistics(course.id, self.db, SimpleNamespace(username="admin"))
        totals = {row["name"]: row["total"] for row in statistics["teachers"]}
        self.assertEqual(totals, {"丙老師": 1, "乙老師": 1, "甲老師": 0})

        effective = get_effective_timetable(date(2026, 8, 10), db=self.db)
        cycle = next(item for item in effective["adjustments"] if item["id"] == swap.id)
        self.assertEqual(len(cycle["legs"]), 2)

        entries = daily_export_data(self.db, date(2026, 8, 10))
        self.assertEqual(entries[0]["rows"][0]["subject"], "中文")
        self.assertEqual(entries[0]["rows"][0]["substitute_teacher"], "乙老師")
        self.assertEqual(entries[0]["rows"][0]["remark"], "與 2026-08-10 第 2 節（乙老師）對調")
        periods = get_period_times(self.db)
        workbook = load_workbook(BytesIO(build_daily_xlsx(entries, periods)))
        self.assertEqual(workbook.sheetnames, ["甲老師"])
        self.assertEqual(workbook["甲老師"]["E7"].value, "乙老師")
        self.assertEqual(workbook["甲老師"]["G7"].value, "與 2026-08-10 第 2 節（乙老師）對調")
        self.assertTrue(build_daily_pdf(entries[0], periods).startswith(b"%PDF"))
        changed_periods = [{**item, "start": "08:20"} if item["period"] == 1 else item for item in periods]
        save_period_times(self.db, changed_periods)
        self.assertEqual(get_period_times(self.db)[0]["start"], "08:20")
        with self.assertRaises(ValueError):
            validate_period_times([{**item, "start": "08:30"} if item["period"] == 2 else item for item in periods])


if __name__ == "__main__":
    unittest.main()
