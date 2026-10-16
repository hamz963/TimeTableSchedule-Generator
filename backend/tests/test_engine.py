"""Engine tests: context, heuristic, optimizer, metrics, pipeline paths."""
from app.engine import objectives as obj
from app.engine.constraints import verify
from app.engine.context import build_context, time_bucket
from app.engine.heuristic import greedy_assign
from app.engine import metrics as metrics_mod
from app.engine.optimizer import optimize
from app.engine.pipeline import solve
from app.services.solver import TimetableSolver
from tests.conftest import make_small_instance


def _structured_instance(n_faculty=20, n_rooms=10, n_courses=60, n_slots=25):
    days = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    hours = [8, 10, 13, 15, 17]
    slots = [
        {"id": i + 1, "day_of_week": days[(i // len(hours)) % 5],
         "start_time": f"{hours[i % len(hours)]:02d}:00",
         "end_time": f"{hours[i % len(hours)] + 1:02d}:00", "duration_minutes": 60}
        for i in range(n_slots)
    ]
    faculty = [
        {"id": i + 1, "name": f"F{i + 1}", "max_hours_per_day": 6, "max_days_per_week": 5,
         "preferences": [slots[(i * 3 + k) % n_slots]["id"] for k in range(4)],
         "unavailable_slots": []}
        for i in range(n_faculty)
    ]
    venues = [
        {"id": i + 1, "name": f"R{i + 1}", "capacity": 40 + (i % 5) * 30,
         "equipment": [], "available_slots": []}
        for i in range(n_rooms)
    ]
    bands = ["Morning", "Afternoon", "Evening", ""]
    courses = [
        {"id": i + 1, "name": f"C{i + 1}", "faculty_id": (i % n_faculty) + 1,
         "capacity_required": 20 + (i % 4) * 15, "duration_minutes": 60,
         "required_equipment": [], "preferred_time": bands[i % 4]}
        for i in range(n_courses)
    ]
    return faculty, venues, slots, courses


def test_context_indexes():
    faculty, venues, slots, courses = make_small_instance()
    ctx = build_context(faculty, venues, slots, courses)
    assert set(ctx.days) == {"Mon", "Tue"}
    assert ctx.slot_by_id[1]["start_time"] == "09:00"
    assert ctx.slot_start[1] == 9 * 60
    assert time_bucket(9 * 60) == "Morning"
    assert time_bucket(14 * 60) == "Afternoon"
    assert time_bucket(18 * 60) == "Evening"


def test_greedy_produces_valid_assignment():
    faculty, venues, slots, courses = make_small_instance()
    ctx = build_context(faculty, venues, slots, courses)
    result = greedy_assign(ctx)
    assert result is not None
    assert verify(result, courses, faculty, venues, slots) == []


def test_optimizer_improves_and_preserves_hard_constraints():
    faculty, venues, slots, courses = _structured_instance()
    ctx = build_context(faculty, venues, slots, courses)
    seed = greedy_assign(ctx)
    assert seed is not None
    start = obj.total_cost(ctx, {a["course_id"]: (a["venue_id"], a["slot_id"]) for a in seed})
    opt = optimize(ctx, seed, time_budget_s=0.6, seed=7)
    assert opt.cost_end <= opt.cost_start  # never worse than the seed
    assert opt.cost_start == round(start, 3)
    # Optimized timetable still satisfies every hard constraint.
    assert verify(opt.assignments, courses, faculty, venues, slots) == []


def test_optimizer_is_deterministic():
    faculty, venues, slots, courses = _structured_instance(n_courses=40)
    ctx = build_context(faculty, venues, slots, courses)
    seed = greedy_assign(ctx)
    # max_iterations => fully deterministic mode (fixed steps, descent to convergence).
    a = optimize(ctx, seed, seed=123, max_iterations=4000)
    b = optimize(ctx, seed, seed=123, max_iterations=4000)
    assert a.cost_end == b.cost_end
    assert {d["course_id"]: (d["venue_id"], d["slot_id"]) for d in a.assignments} == \
           {d["course_id"]: (d["venue_id"], d["slot_id"]) for d in b.assignments}
    # A different seed may explore differently but must never be worse than seed.
    c = optimize(ctx, seed, seed=999, max_iterations=4000)
    assert c.cost_end <= c.cost_start


def test_metrics_score_bounds_and_grade():
    faculty, venues, slots, courses = _structured_instance()
    ctx = build_context(faculty, venues, slots, courses)
    seed = greedy_assign(ctx)
    placement = {a["course_id"]: (a["venue_id"], a["slot_id"]) for a in seed}
    sc = metrics_mod.score(ctx, placement)
    assert 0.0 <= sc["score"] <= 100.0
    assert sc["grade"] in ("poor", "weak", "fair", "good", "excellent")
    explain = metrics_mod.explain(ctx, placement)
    assert "reasons" in explain and "teachers" in explain


def test_pipeline_small_uses_exact_large_uses_heuristic():
    faculty, venues, slots, courses = make_small_instance()
    small = solve(faculty, venues, slots, courses, time_limit_seconds=5)
    assert small.engine["path"] == "exact"
    assert small.status in ("optimal", "feasible")
    assert small.metrics  # quality metrics attached

    # Large instance (est vars > 25k) -> heuristic path with optimizer stats.
    f2, v2, s2, c2 = _structured_instance(n_faculty=40, n_rooms=15, n_courses=120, n_slots=30)
    large = solve(f2, v2, s2, c2, time_limit_seconds=5, rules=None)
    assert large.engine["path"] == "heuristic"
    stats = large.engine["optimizer"]
    assert stats["iterations"] >= 0
    assert verify(large.assignments, c2, f2, v2, s2) == []


def test_facade_backward_compatible():
    faculty, venues, slots, courses = make_small_instance()
    result = TimetableSolver.generate(faculty, venues, slots, courses, time_limit_seconds=5)
    assert result.status in ("optimal", "feasible")
    assert len(result.assignments) == len(courses)
    assert result.metrics and result.engine
    assert TimetableSolver.verify(result.assignments, courses, faculty, venues, slots) == []
