"""Repeatable benchmark for the rescheduling analysis hot path."""

from pathlib import Path
from statistics import median
from sys import argv
from time import perf_counter

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from models import AbsenceCase
from rescheduling_service import analyze_absences, effective_occurrences, teaching_dates


def measure(function, repeats=7):
    function()  # Warm caches before measuring the steady-state request path.
    samples = []
    for _ in range(repeats):
        started = perf_counter()
        function()
        samples.append((perf_counter() - started) * 1000)
    return samples


db_path = Path(argv[1] if len(argv) > 1 else "../data/exemple/gestor.db").resolve()
engine = create_engine(f"sqlite:///{db_path.as_posix()}")
with Session(engine) as db:
    grouped = {}
    for case in db.query(AbsenceCase).all():
        grouped.setdefault(case.data, []).append(case)
    cases = max(grouped.values(), key=len)
    start = cases[0].data
    end = teaching_dates(db, start, 5)[-1]
    benchmarks = {
        "effective_occurrences": lambda: effective_occurrences(db, start, end),
        "analyze_absences": lambda: analyze_absences(db, cases),
    }
    print(f"database={db_path} date={start} cases={len(cases)} repeats=7")
    for name, function in benchmarks.items():
        samples = measure(function)
        print(f"{name}: median={median(samples):.3f} ms min={min(samples):.3f} ms max={max(samples):.3f} ms")
