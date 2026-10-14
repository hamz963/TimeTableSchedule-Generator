"""Request size caps (413) + concurrency/load behavior."""
import statistics
import time
from concurrent.futures import ThreadPoolExecutor

from app.services.solver import TimetableSolver
from app.services.validator import PayloadTooLargeError, validate_generate_request
from tests.conftest import make_small_instance
from tests.shared import get_client

client = get_client()


def test_oversized_advanced_payload_rejected():
    faculty, venues, slots, courses = make_small_instance()
    big_faculty = [{**faculty[0], "id": i, "name": f"F{i}"} for i in range(1, 1601)]
    payload = {"faculty": big_faculty, "venues": venues, "slots": slots, "courses": courses}
    try:
        validate_generate_request(payload)
    except PayloadTooLargeError as exc:
        assert "max 1000" in str(exc)
        return
    raise AssertionError("expected PayloadTooLargeError")


def test_oversized_simple_payload_returns_413():
    r = client.post("/schedule/generate-simple", json={
        "teachers": [{"name": f"T{i}"} for i in range(1001)],
        "courses": [{"name": "C", "teacher": "T0", "credit_hours": 1}],
        "rooms": [],
        "days": ["Mon"],
        "day_start": "08:00",
        "day_end": "09:00",
        "period_minutes": 60,
        "gap_minutes": 0,
        "lunch_break": False,
    })
    assert r.status_code == 413
    assert "max 1000" in r.json()["detail"]


def _tiny_problem():
    faculty = [{"id": 1, "name": "A", "max_hours_per_day": 6, "max_days_per_week": 5,
                "preferences": [], "unavailable_slots": []}]
    venues = [{"id": 1, "name": "R", "capacity": 30, "equipment": [], "available_slots": []}]
    slots = [{"id": 1, "day_of_week": "Mon", "start_time": "09:00", "end_time": "10:00",
              "duration_minutes": 60}]
    courses = [{"id": 1, "name": "C", "code": "C1", "faculty_id": 1, "capacity_required": 10,
                "duration_minutes": 60, "required_equipment": []}]
    return faculty, venues, slots, courses


def test_solver_parallel_throughput():
    """8 threads x solvers: all optimal, none starved (GIL-friendly CP-SAT)."""
    faculty, venues, slots, courses = _tiny_problem()

    def one(_):
        return TimetableSolver.generate(faculty, venues, slots, courses,
                                        time_limit_seconds=5)

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(one, range(8)))
    wall = time.perf_counter() - t0
    assert all(r.status in ("optimal", "feasible") for r in results)
    assert all(len(r.assignments) == 1 for r in results)
    assert wall < 30, f"8 parallel solves took {wall:.1f}s"


def test_api_latency_distribution():
    """20 sequential small generations: all 200, p95 latency bounded."""
    payload = {
        "teachers": [{"name": "Alice"}],
        "courses": [{"name": "Math", "teacher": "Alice", "credit_hours": 1}],
        "rooms": [],
        "days": ["Mon"],
        "day_start": "08:00",
        "day_end": "10:00",
        "period_minutes": 60,
        "gap_minutes": 10,
        "lunch_break": False,
    }
    latencies = []
    for _ in range(20):
        t0 = time.perf_counter()
        r = client.post("/schedule/generate-simple", json=payload)
        latencies.append(time.perf_counter() - t0)
        assert r.status_code == 200, r.text
    p95 = statistics.quantiles(latencies, n=20)[18]
    assert p95 < 5.0, f"p95 latency {p95:.2f}s too high"
    print(f"\napi latency: p50={statistics.median(latencies):.3f}s p95={p95:.3f}s")
