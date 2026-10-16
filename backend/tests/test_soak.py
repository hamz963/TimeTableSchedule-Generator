"""Soak / load behavior: large instances and bounded concurrency.

These exercise the large-instance heuristic path and concurrent solves, and
print real numbers. Bounds are deliberately generous (CI machines vary); the
point is to prove correctness and bounded time at scale, not to benchmark a
specific CPU.
"""
import statistics
import time
from concurrent.futures import ThreadPoolExecutor

from app.engine.constraints import verify
from app.services.solver import TimetableSolver
from tests.shared import get_client

client = get_client()


def _big(faculty_n: int, rooms_n: int, courses_n: int, slots_n: int):
    days = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    hours = [8, 9, 10, 11, 12, 13, 14, 15]
    slots = [
        {"id": i + 1, "day_of_week": days[(i // len(hours)) % 5],
         "start_time": f"{hours[i % len(hours)]:02d}:00",
         "end_time": f"{hours[i % len(hours)] + 1:02d}:00", "duration_minutes": 60}
        for i in range(slots_n)
    ]
    faculty = [
        {"id": i + 1, "name": f"F{i + 1}", "max_hours_per_day": 6, "max_days_per_week": 5,
         "preferences": [], "unavailable_slots": []}
        for i in range(faculty_n)
    ]
    venues = [
        {"id": i + 1, "name": f"R{i + 1}", "capacity": 120, "equipment": [], "available_slots": []}
        for i in range(rooms_n)
    ]
    bands = ["Morning", "Afternoon", "", ""]
    courses = [
        {"id": i + 1, "name": f"C{i + 1}", "code": f"C{i + 1:05d}",
         "faculty_id": (i % faculty_n) + 1, "capacity_required": 30,
         "duration_minutes": 60, "required_equipment": [], "preferred_time": bands[i % 4]}
        for i in range(courses_n)
    ]
    return faculty, venues, slots, courses


def test_soak_200_faculty_solves_with_no_violations():
    """200 faculty / 40 rooms / 400 courses -> feasible, zero hard violations."""
    faculty, venues, slots, courses = _big(200, 40, 400, 60)
    t0 = time.perf_counter()
    result = TimetableSolver.generate(
        faculty, venues, slots, courses, time_limit_seconds=5,
    )
    elapsed = time.perf_counter() - t0
    violations = verify(result.assignments, courses, faculty, venues, slots)
    engine = result.engine or {}
    stats = engine.get("optimizer", {})
    print(f"\nsoak(200/40/400/60): status={result.status} path={engine.get('path')} "
          f"scheduled={len(result.assignments)}/{len(courses)} wall={elapsed:.2f}s "
          f"iters={stats.get('iterations')} score={stats.get('best_score')} "
          f"converged={stats.get('converged')}")
    assert result.status in ("optimal", "feasible"), result.status
    assert len(result.assignments) == len(courses)
    assert violations == [], violations[:5]
    assert elapsed < 90, f"200-faculty solve took {elapsed:.1f}s"


def test_soak_concurrent_solves_are_independent():
    """64 concurrent solves of the same medium instance: all feasible, no bleed."""
    faculty, venues, slots, courses = _big(40, 20, 100, 40)

    def one(_):
        return TimetableSolver.generate(faculty, venues, slots, courses,
                                        time_limit_seconds=5)

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=16) as ex:
        results = list(ex.map(one, range(64)))
    wall = time.perf_counter() - t0
    ok = [r for r in results if r.status in ("optimal", "feasible")]
    violations = verify(ok[0].assignments, courses, faculty, venues, slots)
    print(f"\nsoak(64 concurrent medium solves): ok={len(ok)}/64 wall={wall:.2f}s "
          f"p50_engine_ms={statistics.median(r.solver_time_ms for r in ok):.0f}")
    assert len(ok) == 64
    assert violations == []
    assert wall < 120, f"64 concurrent solves took {wall:.1f}s"


def test_soak_api_latency_distribution_under_load():
    """80 sequential API generations: all 200, p95 bounded."""
    payload = {
        "teachers": [{"name": f"T{i}"} for i in range(6)],
        "courses": [{"name": f"C{i}", "teacher": f"T{i % 6}", "credit_hours": 2} for i in range(12)],
        "rooms": [], "days": ["Mon", "Tue", "Wed", "Thu", "Fri"],
        "day_start": "08:00", "day_end": "16:00", "period_minutes": 60,
        "gap_minutes": 10, "lunch_break": True, "lunch_start": "12:00", "lunch_end": "13:00",
    }
    latencies = []
    for _ in range(80):
        t0 = time.perf_counter()
        r = client.post("/schedule/generate-simple", json=payload)
        latencies.append(time.perf_counter() - t0)
        assert r.status_code == 200, r.text
    p95 = statistics.quantiles(latencies, n=20)[18]
    print(f"\nsoak(api): n=80 p50={statistics.median(latencies):.3f}s p95={p95:.3f}s "
          f"max={max(latencies):.3f}s")
    assert p95 < 5.0, f"p95 latency {p95:.2f}s too high"
