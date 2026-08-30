import inspect
import json
import os
import sys
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("SECRET_KEY", "permission-guard-tests-only-secret-key")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from auth_utils import get_current_user, require_any_permission, require_permission  # noqa: E402
from models import (  # noqa: E402
    AbsenceCase,
    Base,
    Professor,
    ScheduleAdjustment,
    ScheduleAdjustmentLeg,
    TimetableLesson,
    TimetableVersion,
)
from routes import rescheduling  # noqa: E402
from routes.rescheduling import (  # noqa: E402
    AbsenceBatchCreateRequest,
    AbsenceCreateRequest,
    analyze,
    cancel_absence,
    create_absences_batch,
    update_absence,
)


def _user(username="user", permissions=(), role="user"):
    return SimpleNamespace(
        username=username,
        role=role,
        permissions=json.dumps(list(permissions)),
    )


@pytest.mark.parametrize(
    ("user", "path", "status_code"),
    [
        (_user(permissions=[]), "/single", 403),
        (_user(permissions=["statistics.view"]), "/single", 200),
        (_user(permissions=[]), "/any", 403),
        (_user(permissions=["timetable.upload"]), "/any", 200),
        (_user(role="admin"), "/single", 200),
        (_user(role="admin"), "/any", 200),
    ],
)
def test_permission_dependencies_return_403_and_keep_admin_compatibility(user, path, status_code):
    app = FastAPI()

    @app.get("/single")
    def single(_current_user=Depends(require_permission("statistics.view"))):
        return {"ok": True}

    @app.get("/any")
    def any_permission(_current_user=Depends(require_any_permission("timetable.upload", "timetable.manage"))):
        return {"ok": True}

    app.dependency_overrides[get_current_user] = lambda: user
    assert TestClient(app).get(path).status_code == status_code


def _route_guards(method: str, path: str) -> set[tuple[str, tuple[str, ...]]]:
    route = next(
        route for route in rescheduling.router.routes
        if route.path == path and method in route.methods
    )
    guards = set()
    for dependency in route.dependant.dependencies:
        values = inspect.getclosurevars(dependency.call).nonlocals
        if "permission" in values:
            guards.add(("all", (values["permission"],)))
        if "permissions" in values:
            guards.add(("any", tuple(values["permissions"])))
    return guards


@pytest.mark.parametrize(
    ("method", "path", "expected"),
    [
        ("GET", "/api/timetables", {("any", ("workbench.view", "timetable.upload", "timetable.manage"))}),
        ("GET", "/api/timetables/current", {("any", ("workbench.view", "timetable.upload", "timetable.manage"))}),
        ("PUT", "/api/timetables/{version_id}", {("all", ("timetable.manage",))}),
        ("DELETE", "/api/timetables/{version_id}", {("all", ("timetable.manage",))}),
        ("POST", "/api/timetables/import/preview", {("all", ("timetable.upload",))}),
        ("POST", "/api/timetables/import/{preview_id}/activate", {("all", ("timetable.manage",))}),
        ("DELETE", "/api/timetables/import/{preview_id}", {("all", ("timetable.upload",))}),
        ("PUT", "/api/timetables/import/{preview_id}/resolutions", {("all", ("timetable.upload",))}),
        ("GET", "/api/rescheduling/teachers", {("any", ("workbench.view", "records.manage"))}),
        ("GET", "/api/rescheduling/statistics", {("all", ("statistics.view",))}),
        ("GET", "/api/rescheduling/exports/daily.xlsx", {("all", ("exports.download",))}),
        ("GET", "/api/rescheduling/exports/daily.pdf", {("all", ("exports.download",))}),
        ("POST", "/api/absence-cases", {("all", ("absence.create",))}),
        ("POST", "/api/absence-cases/batch", {("all", ("absence.create",))}),
        ("POST", "/api/absence-cases/cancel-batch", {("any", ("absence.create", "records.manage"))}),
        ("PUT", "/api/absence-cases/{absence_id}", {("any", ("absence.create", "records.manage"))}),
        ("DELETE", "/api/absence-cases/{absence_id}", {("any", ("absence.create", "records.manage"))}),
        ("DELETE", "/api/absence-cases/{absence_id}/purge", {("all", ("records.manage",)), ("all", ("records.view",))}),
        ("GET", "/api/absence-cases", {("all", ("workbench.view",))}),
        ("POST", "/api/absence-cases/{absence_id}/analyze", {("all", ("absence.create",))}),
        ("GET", "/api/manual-arrangements", {("all", ("manual_arrangement.manage",)), ("all", ("workbench.view",))}),
        ("POST", "/api/manual-arrangements/cover", {("all", ("manual_arrangement.manage",)), ("all", ("workbench.view",))}),
        ("POST", "/api/adjustments/confirm", {("all", ("adjustment.confirm",))}),
        ("POST", "/api/adjustments/manual", {("all", ("manual_arrangement.manage",)), ("all", ("workbench.view",))}),
        ("GET", "/api/adjustments", {("all", ("records.view",))}),
        ("PUT", "/api/adjustments/{adjustment_id}", {("all", ("records.manage",)), ("all", ("records.view",))}),
        ("DELETE", "/api/adjustments/{adjustment_id}", {("all", ("records.manage",)), ("all", ("records.view",))}),
        ("POST", "/api/adjustments/{adjustment_id}/revert", {("all", ("records.manage",)), ("all", ("records.view",))}),
        ("GET", "/api/records", {("all", ("records.view",))}),
        ("GET", "/api/effective-timetable", {("all", ("workbench.view",))}),
        ("GET", "/api/calendar/closures", {("all", ("workbench.view",))}),
    ],
)
def test_business_routes_use_the_planned_permission_guards(method, path, expected):
    assert _route_guards(method, path) == expected


@pytest.fixture
def absence_data():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    teacher = Professor(nom="A老師", actiu=True)
    version = TimetableVersion(
        effective_from=date(2026, 8, 10),
        effective_to=date(2026, 8, 31),
        class_filename="classes.xls",
        teacher_filename="teachers.xlsx",
        active=True,
    )
    db.add_all([teacher, version])
    db.flush()
    lessons = [
        TimetableLesson(
            version_id=version.id,
            weekday=weekday,
            period=period,
            class_code="1A",
            subject="中文",
            teachers_json=json.dumps([teacher.id]),
        )
        for weekday, period in ((0, 1), (0, 2), (1, 1))
    ]
    owned = AbsenceCase(
        professor_id=teacher.id,
        data=date(2026, 8, 10),
        periods_json="[1]",
        status="resolved",
        created_by="alice",
    )
    withdrawable = AbsenceCase(
        professor_id=teacher.id,
        data=date(2026, 8, 11),
        periods_json="[1]",
        status="open",
        created_by="alice",
    )
    db.add_all([*lessons, owned, withdrawable])
    db.flush()
    adjustment = ScheduleAdjustment(
        absence_case_id=owned.id,
        kind="direct_swap",
        status="confirmed",
        locked=True,
    )
    db.add(adjustment)
    db.flush()
    db.add(ScheduleAdjustmentLeg(
        adjustment_id=adjustment.id,
        lesson_id=lessons[0].id,
        class_code="1A",
        subject="中文",
        teachers_json=json.dumps([teacher.id]),
        from_date=owned.data,
        from_period=1,
        to_date=owned.data,
        to_period=2,
    ))
    db.commit()
    yield db, teacher, owned, withdrawable, adjustment
    db.close()


def test_absence_creator_cannot_edit_others_or_bypass_confirmed_lock(absence_data):
    db, teacher, owned, _, adjustment = absence_data
    request = AbsenceCreateRequest(
        professor_id=teacher.id,
        data=owned.data,
        periods=[2],
        reason_type="sick",
    )
    creator = _user("alice", ["workbench.view", "absence.create"])
    other = _user("bob", ["workbench.view", "absence.create"])
    manager = _user("manager", ["records.view", "records.manage"])

    with pytest.raises(rescheduling.HTTPException) as forbidden:
        update_absence(owned.id, request, db, other)
    assert forbidden.value.status_code == 403

    reason_request = AbsenceCreateRequest(
        professor_id=teacher.id,
        data=owned.data,
        periods=[1],
        reason_type="personal",
    )
    assert update_absence(owned.id, reason_request, db, creator)["success"] is True
    assert db.get(ScheduleAdjustment, adjustment.id) is not None
    assert owned.status == "resolved"

    with pytest.raises(rescheduling.HTTPException) as locked:
        update_absence(owned.id, request, db, creator)
    assert locked.value.status_code == 409

    assert update_absence(owned.id, request, db, manager)["success"] is True
    assert db.get(ScheduleAdjustment, adjustment.id) is None


def test_only_creator_or_record_manager_can_withdraw_absence(absence_data):
    db, _, _, withdrawable, _ = absence_data
    other = _user("bob", ["workbench.view", "absence.create"])
    manager = _user("manager", ["records.view", "records.manage"])

    with pytest.raises(rescheduling.HTTPException) as forbidden:
        cancel_absence(withdrawable.id, db, other)
    assert forbidden.value.status_code == 403

    assert cancel_absence(withdrawable.id, db, manager)["success"] is True


def test_batch_create_cannot_update_another_creators_case(absence_data):
    db, teacher, owned, _, _ = absence_data
    other = _user("bob", ["workbench.view", "absence.create"])
    request = AbsenceBatchCreateRequest(items=[AbsenceCreateRequest(
        professor_id=teacher.id,
        data=owned.data,
        periods=[2],
        reason_type="sick",
    )])

    with pytest.raises(rescheduling.HTTPException) as forbidden:
        create_absences_batch(request, db, other)
    assert forbidden.value.status_code == 403


def test_absence_creator_cannot_analyze_or_reuse_locked_case(absence_data):
    db, teacher, owned, withdrawable, _ = absence_data
    creator = _user("alice", ["workbench.view", "absence.create"])
    other = _user("bob", ["workbench.view", "absence.create"])

    with pytest.raises(rescheduling.HTTPException) as forbidden:
        analyze(withdrawable.id, db, other)
    assert forbidden.value.status_code == 403

    with pytest.raises(rescheduling.HTTPException) as locked_analysis:
        analyze(owned.id, db, creator)
    assert locked_analysis.value.status_code == 409

    with pytest.raises(rescheduling.HTTPException) as locked_reuse:
        create_absences_batch(
            AbsenceBatchCreateRequest(items=[AbsenceCreateRequest(
                professor_id=teacher.id,
                data=owned.data,
                periods=[1],
                reason_type="sick",
            )]),
            db,
            creator,
        )
    assert locked_reuse.value.status_code == 409
