"""Isolated HTTP write-flow benchmark; never pass a live writable database."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import sqlite3
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter
from urllib.error import HTTPError

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from benchmark_rescheduling import http_requests, seed
from models import Base, AbsenceCase
from rescheduling_service import effective_occurrences, analyze_absences


def stable(value):
    # Wall-clock persistence metadata differs between independent replays.
    if isinstance(value, dict):
        return {k: stable(v) for k, v in value.items()
                if k not in {"created_at", "updated_at", "confirmed_at"}}
    if isinstance(value, list):
        return [stable(v) for v in value]
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--save-results", type=Path)
    parser.add_argument("--compare-results", type=Path)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    assert args.repeats > 0
    report, results = {}, {}
    with TemporaryDirectory() as root:
        source = Path(root) / "source.db"
        if args.database:
            with closing(sqlite3.connect(args.database.resolve().as_uri() + "?mode=ro", uri=True)) as src:
                with closing(sqlite3.connect(source)) as dst:
                    src.backup(dst)
        engine = create_engine(f"sqlite:///{source.as_posix()}")
        if not args.database:
            Base.metadata.create_all(engine)
        with Session(engine) as db:
            if not args.database:
                seed(db, 1000)
            start = date(2026, 6, 10) if args.database else date(2026, 9, 7)
            days, teachers = [], {}
            for offset in range(1, 22):
                day = start + timedelta(days=offset)
                if db.query(AbsenceCase).filter_by(data=day).count():
                    continue
                ids = sorted({int(t) for row in effective_occurrences(db, day, day)
                              if row["lesson_id"] is not None for t in row["teachers"]})
                if len(ids) >= 3:
                    # Select a teacher with a confirmable suggestion so the write chain is exercised.
                    chosen = None
                    for teacher in ids:
                        probe = AbsenceCase(id=-1, professor_id=teacher, data=day,
                                            periods_json="[1,2,3,4,5,6,7,8,9]", status="open")
                        analysis = analyze_absences(db, [probe], now=datetime.combine(day, datetime.min.time()))
                        if any(t.get("recommended") for t in analysis["tasks"]):
                            chosen = teacher
                            break
                    if chosen is None:
                        continue
                    ids = [chosen, *[t for t in ids if t != chosen]]
                    days.append(day)
                    teachers[day] = ids
                if len(days) == 3:
                    break
            assert len(days) == 3, "Need three teaching dates without existing absences"
        engine.dispose()
        scenarios = {"single": [(days[0], teachers[days[0]][0])],
                     "same_day_three": [(days[0], t) for t in teachers[days[0]][:3]],
                     "three_dates": [(day, teachers[day][0]) for day in days]}
        for name, entries in scenarios.items():
            samples = {}
            expected = None
            for repeat in range(args.repeats + 1):
                with TemporaryDirectory(dir=root) as directory:
                    with http_requests(directory, source, days[0], None, raw_request=True) as request:
                        output, elapsed = {}, {}

                        def measure(label, function):
                            begun = perf_counter()
                            value = function()
                            elapsed[label] = (perf_counter() - begun) * 1000
                            output[label] = value
                            return value

                        created = measure("create_and_analyze", lambda: request(
                            "/api/absence-cases/batch", "POST", {"items": [
                                {"professor_id": t, "data": str(day), "periods": list(range(1, 10)),
                                 "reason_type": "sick"} for day, t in entries]}))
                        assert len(created["created_absence_case_ids"]) == len(entries)
                        analysis = created["analyses"][0]
                        task = next(t for t in analysis["tasks"] if t.get("recommended"))
                        candidate = task["recommended"]
                        verify_dates = sorted({leg[k] for leg in candidate["legs"] for k in ("from_date", "to_date")})

                        def verify():
                            with ThreadPoolExecutor(max_workers=len(verify_dates)) as pool:
                                return list(pool.map(lambda d: request(f"/api/effective-timetable?data={d}"), verify_dates))

                        measure("verify_timetables", verify)
                        body = {"absence_case_id": task["absence_case_id"], "candidate_id": candidate["id"],
                                "expected_revision": analysis["revision"]}
                        confirmed = measure("confirm", lambda: request("/api/adjustments/confirm", "POST", body))
                        assert confirmed["revision"] > analysis["revision"]
                        assert task["task_key"] not in {t["task_key"] for t in confirmed["analysis"]["tasks"]}
                        measure("refresh", lambda: [request(f"/api/timetables/current?data={days[0]}"),
                                                     request(f"/api/effective-timetable?data={days[0]}")])
                        # A double click with the stale revision must not create another adjustment.
                        try:
                            request("/api/adjustments/confirm", "POST", body)
                            raise AssertionError("Stale confirmation accepted")
                        except HTTPError as error:
                            assert error.code == 409
                        output["persisted_absences"] = request(f"/api/absence-cases?data={days[0]}")
                        actual = stable(output)
                        if expected is None:
                            expected = actual
                        assert actual == expected, f"Non-deterministic flow: {name}"
                        elapsed["total"] = sum(elapsed.values())
                        if repeat:
                            for label, ms in elapsed.items():
                                samples.setdefault(label, []).append(round(ms, 3))
            results[name] = expected
            report[name] = {label: {"median_ms": round(median(values), 3), "samples_ms": values}
                            for label, values in samples.items()}
            print(name, json.dumps(report[name]), flush=True)
    if args.compare_results:
        assert results == json.loads(args.compare_results.read_text()), "Before/after business results differ"
        print("Exact business-result comparison passed; timestamps excluded.", flush=True)
    if args.save_results:
        args.save_results.write_text(json.dumps(results, ensure_ascii=False), encoding="utf-8")
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
