"""Performance benchmarks: solver time vs problem size."""
import time
from app.services.solver import TimetableSolver


def _instance(n_faculty: int, n_rooms: int, n_courses: int, n_slots: int = 20):
    days = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    slots = [
        {"id": i + 1, "day_of_week": days[(i // 4) % 5],
         "start_time": f"{9 + (i % 4):02d}:00", "end_time": f"{10 + (i % 4):02d}:00",
         "duration_minutes": 60}
        for i in range(n_slots)
    ]
    faculty = [
        {"id": i + 1, "name": f"F{i + 1}", "max_hours_per_day": 6,
         "max_days_per_week": 5, "preferences": [], "unavailable_slots": []}
        for i in range(n_faculty)
    ]
    venues = [
        {"id": i + 1, "name": f"R{i + 1}", "capacity": 100,
         "equipment": [], "available_slots": []}
        for i in range(n_rooms)
    ]
    courses = [
        {"id": i + 1, "name": f"C{i + 1}", "code": f"C{i + 1:04d}",
         "faculty_id": (i % n_faculty) + 1, "capacity_required": 30,
         "duration_minutes": 60, "required_equipment": []}
        for i in range(n_courses)
    ]
    return faculty, venues, slots, courses


def test_perf_medium_50x20x100():
    """Acceptance: 50 faculty / 20 rooms / 100 courses solves in <5s."""
    faculty, venues, slots, courses = _instance(50, 20, 100, n_slots=40)
    started = time.perf_counter()
    result = TimetableSolver.generate(faculty, venues, slots, courses, time_limit_seconds=5)
    elapsed = time.perf_counter() - started
    print(f"\nmedium(50/20/100): status={result.status} solver_ms={result.solver_time_ms} "
          f"wall={elapsed:.2f}s scheduled={len(result.assignments)}")
    assert result.status in ("optimal", "feasible")
    assert elapsed < 5.0
    # 100% hard-constraint satisfaction on the returned timetable.
    violations = TimetableSolver.verify(result.assignments, courses, faculty, venues, slots)
    assert violations == [], violations


def test_perf_small_scales():
    for n in (5, 20):
        faculty, venues, slots, courses = _instance(5, 3, n)
        result = TimetableSolver.generate(faculty, venues, slots, courses, time_limit_seconds=5)
        assert result.status in ("optimal", "feasible")
        assert len(result.assignments) == n
