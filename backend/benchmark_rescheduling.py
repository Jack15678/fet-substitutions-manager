"""Repeatable, isolated request benchmarks; run with --help for options."""

import argparse
import cProfile
import json
import os
import platform
import pstats
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
from contextlib import closing, contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter, sleep
from urllib.error import URLError
from urllib.request import Request, urlopen
from unittest.mock import patch

import sqlalchemy
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from models import (AbsenceCase, Base, Professor, ScheduleAdjustment,
                    ScheduleAdjustmentLeg, TimetableLesson, TimetableTeacherSlot,
                    TimetableVersion)
from rescheduling_service import analyze_absences, effective_occurrences, teaching_dates


def seed(db, history):
    """30 classes, 60 teachers, 9 periods/day, 4 simultaneous absences."""
    start = date(2026, 9, 7)
    db.add_all(Professor(id=i, nom=f"Teacher {i:02}", actiu=True) for i in range(1, 61))
    db.add(TimetableVersion(id=1, effective_from=date(2025, 9, 1),
                           class_filename="classes.xls", teacher_filename="teachers.xlsx", active=True))
    lessons = []
    for weekday in range(5):
        for period in range(1, 10):
            for cls in range(30):
                teacher = (cls + period * 7 + weekday * 11) % 60 + 1
                lesson = TimetableLesson(
                    id=len(lessons) + 1, version_id=1, weekday=weekday, period=period,
                    class_code=f"{cls // 5 + 1}{chr(65 + cls % 5)}",
                    subject=("中文", "英文", "數學")[teacher % 3], teachers_json=json.dumps([teacher]),
                )
                lessons.append(lesson)
                db.add(TimetableTeacherSlot(version_id=1, professor_id=teacher, weekday=weekday,
                                           period=period, class_code=lesson.class_code, subject=lesson.subject))
    db.add_all(lessons)
    for i in range(history):
        day_offset, period_offset = divmod(i, 5)
        day = date(2025, 9, 1) + timedelta(weeks=day_offset // 5, days=day_offset % 5)
        lesson = lessons[day.weekday() * 270 + period_offset * 30 + day_offset % 30]
        teacher = json.loads(lesson.teachers_json)[0]
        db.add(ScheduleAdjustment(id=i + 1, kind="emergency_cover", status="confirmed",
                                  confirmed_at=datetime.combine(day, datetime.min.time())))
        db.add(ScheduleAdjustmentLeg(
            adjustment_id=i + 1, lesson_id=lesson.id, class_code=lesson.class_code,
            subject=lesson.subject, teachers_json=lesson.teachers_json,
            from_date=day, to_date=day, from_period=lesson.period, to_period=lesson.period,
            replaced_teacher_id=teacher, replacement_teacher_id=(teacher + 30 - 1) % 60 + 1,
        ))
    db.add_all(AbsenceCase(professor_id=i, data=start, periods_json="[1,2,3,4,5,6,7,8,9]",
                          status="open", reason_type="sick") for i in range(1, 5))
    db.commit()
    return start


@contextmanager
def http_requests(directory, db_path, start, absence_id, raw_request=False):
    """Run the real ASGI app on loopback against a disposable DB and auth account."""
    data = Path(directory) / "benchmark"
    data.mkdir(exist_ok=True)
    shutil.copyfile(db_path, data / "gestor.db")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    password = secrets.token_urlsafe(32)
    env = {**os.environ, "DATA_DIR": directory, "AUTH_DB_PATH": str(Path(directory) / "http-auth.db"),
           "APP_INSTITUCIO": "benchmark", "ADMIN_INSTITUCIO": "benchmark", "ADMIN_USERNAME": "benchmark",
           "ADMIN_PASSWORD": password, "SECRET_KEY": secrets.token_hex(32),
           "ENVIRONMENT": "production", "COOKIE_SECURE": "false", "BENCHMARK_DATE": start.isoformat()}
    code = (
        "import os; from datetime import datetime; import routes.rescheduling as routes; "
        "now = datetime.fromisoformat(os.environ['BENCHMARK_DATE']); "
        "routes.hong_kong_now = lambda: now; routes.hong_kong_today = lambda: now.date(); "
        f"import main, uvicorn; uvicorn.run(main.app, host='127.0.0.1', port={port}, access_log=False)"
    )
    base = f"http://127.0.0.1:{port}"
    with open(Path(directory) / "http-server.log", "w+") as log:
        process = subprocess.Popen([sys.executable, "-c", code], env=env, stdout=log, stderr=log)
        try:
            deadline = perf_counter() + 20
            while True:
                try:
                    with urlopen(base + "/api/health", timeout=1) as response:
                        assert response.status == 200
                    break
                except URLError:
                    if process.poll() is not None or perf_counter() > deadline:
                        log.seek(0)
                        raise RuntimeError("Benchmark HTTP server failed: " + log.read()[-2000:])
                    sleep(0.1)
            login = Request(base + "/api/login", data=json.dumps({"username": "benchmark", "password": password}).encode(),
                            headers={"Content-Type": "application/json"})
            with urlopen(login, timeout=30) as response:
                cookie = response.headers["Set-Cookie"].split(";", 1)[0]

            def request(path, method="GET", body=None):
                payload = json.dumps(body).encode() if body is not None else None
                with urlopen(Request(base + path, method=method, data=payload,
                                     headers={"Cookie": cookie, "Content-Type": "application/json"}), timeout=120) as response:
                    return json.load(response)

            yield request if raw_request else {
                "effective_timetable": lambda: request(f"/api/effective-timetable?data={start}"),
                "analyze_absences": lambda: request(f"/api/absence-cases/{absence_id}/analyze", "POST"),
                "manual_arrangements": lambda: request("/api/manual-arrangements"),
                "records": lambda: request("/api/records"),
            }
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", nargs="?", type=Path, help="Optional local DB (read-only snapshot); default: synthetic school")
    parser.add_argument("--history", type=int, default=1000, help="Historical covers in the synthetic school")
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--output", type=Path, help="Write timings and query counts as JSON")
    parser.add_argument("--save-results", type=Path, help="Save full results for exact before/after comparison (may contain private data)")
    parser.add_argument("--compare-results", type=Path, help="Assert exact equality with saved results")
    parser.add_argument("--profile", action="store_true", help="Print top cumulative costs after timed runs")
    parser.add_argument("--http", action="store_true", help="Also measure authenticated HTTP requests to an isolated app")
    args = parser.parse_args()
    if args.repeats < 1 or not 0 <= args.history <= 1300:
        parser.error("repeats must be positive; history must be between 0 and 1300 (before the absence date)")

    with TemporaryDirectory(prefix="rescheduling-benchmark-") as directory:
        db_path = Path(directory) / "gestor.db"
        # Route imports require auth configuration; never use the live auth database.
        with patch.dict(os.environ, {"SECRET_KEY": secrets.token_hex(32), "DATA_DIR": directory,
                                     "AUTH_DB_PATH": str(Path(directory) / "auth.db")}):
            from routes.rescheduling import _manual_arrangements
        if args.database:
            with closing(sqlite3.connect(args.database.resolve().as_uri() + "?mode=ro", uri=True)) as source:
                with closing(sqlite3.connect(db_path)) as destination:
                    source.backup(destination)
        engine = create_engine(f"sqlite:///{db_path.as_posix()}", poolclass=NullPool)
        if not args.database:
            Base.metadata.create_all(engine)
        with Session(engine) as db:
            if not args.database:
                start = seed(db, args.history)
            else:
                grouped = {}
                for case in db.query(AbsenceCase).filter(AbsenceCase.status.in_(("open", "resolved"))).all():
                    grouped.setdefault(case.data, []).append(case)
                if not grouped:
                    parser.error("The database needs at least one active or resolved absence")
                start = max(grouped, key=lambda day: len(grouped[day]))
            end = teaching_dates(db, start, 5)[-1]
            absence_id = db.query(AbsenceCase.id).filter(
                AbsenceCase.data == start, AbsenceCase.status.in_(("open", "resolved")),
            ).order_by(AbsenceCase.id).first()[0]
            counts = {model.__tablename__: db.query(model).count() for model in (
                Professor, TimetableLesson, TimetableTeacherSlot, AbsenceCase, ScheduleAdjustmentLeg,
            )}

        query_count = 0

        @event.listens_for(engine, "before_cursor_execute")
        def count_query(*_):
            nonlocal query_count
            query_count += 1

        def request(name):
            # Match production: a fresh session/connection, no result cache between requests.
            with Session(engine, autoflush=False) as db:
                if name == "effective_day":
                    return effective_occurrences(db, start, start)
                if name == "effective_week":
                    return effective_occurrences(db, start, end)
                if name == "manual_arrangements":
                    return _manual_arrangements(db)
                cases = db.query(AbsenceCase).filter(
                    AbsenceCase.data == start, AbsenceCase.status.in_(("open", "resolved")),
                ).order_by(AbsenceCase.id).all()
                return analyze_absences(db, cases)

        report = {"python": platform.python_version(), "platform": platform.platform(),
                  "sqlalchemy": sqlalchemy.__version__, "sqlite": sqlite3.sqlite_version,
                  "dataset": "snapshot" if args.database else "synthetic", "date": str(start),
                  "counts": counts, "repeats": args.repeats, "benchmarks": {}}
        results = {}
        with patch("routes.rescheduling.hong_kong_now", return_value=datetime.combine(start, datetime.min.time())):
            for name in ("effective_day", "effective_week", "analyze_absences", "manual_arrangements"):
                expected = request(name)  # Warm up imports/SQL compilation, outside measurements.
                samples, queries = [], []
                for _ in range(args.repeats):
                    query_count = 0
                    started = perf_counter()
                    actual = request(name)
                    samples.append((perf_counter() - started) * 1000)
                    queries.append(query_count)
                    assert actual == expected, f"Non-deterministic result: {name}"
                results[name] = expected
                report["benchmarks"][name] = {
                    "median_ms": round(median(samples), 3), "min_ms": round(min(samples), 3),
                    "max_ms": round(max(samples), 3), "samples_ms": [round(value, 3) for value in samples],
                    "queries": queries,
                }
                if args.profile:
                    profile = cProfile.Profile()
                    profile.runcall(request, name)
                    print(f"\nPROFILE {name}")
                    pstats.Stats(profile).strip_dirs().sort_stats("cumtime").print_stats(15)
        if args.http:
            report["http_benchmarks"] = {}
            with http_requests(directory, db_path, start, absence_id) as requests:
                for name, function in requests.items():
                    expected = function()
                    samples = []
                    for _ in range(args.repeats):
                        started = perf_counter()
                        actual = function()
                        samples.append((perf_counter() - started) * 1000)
                        assert actual == expected, f"Non-deterministic HTTP result: {name}"
                    results[f"http_{name}"] = expected
                    report["http_benchmarks"][name] = {
                        "median_ms": round(median(samples), 3), "min_ms": round(min(samples), 3),
                        "max_ms": round(max(samples), 3), "samples_ms": [round(value, 3) for value in samples],
                    }
        serialized = json.loads(json.dumps(results, default=str, ensure_ascii=False))
        if args.compare_results:
            assert serialized == json.loads(args.compare_results.read_text(encoding="utf-8")), "Results changed"
            print("Exact before/after result comparison passed.")
        if args.save_results:
            args.save_results.write_text(json.dumps(serialized, ensure_ascii=False), encoding="utf-8")
        text = json.dumps(report, indent=2)
        if args.output:
            args.output.write_text(text + "\n", encoding="utf-8")
        print(text)
        engine.dispose()


if __name__ == "__main__":
    main()
