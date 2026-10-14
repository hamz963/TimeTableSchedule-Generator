"""Solver unit tests: feasibility, hard constraints, edge cases."""
from app.services.solver import TimetableSolver
from tests.conftest import make_small_instance


def _assert_no_hard_violations(assignments, faculty, venues, slots, courses):
    slot_of = {}
    venue_of = {}
    fac_by_course = {c["id"]: c["faculty_id"] for c in courses}
    fac_unavail = {f["id"]: set(f.get("unavailable_slots", [])) for f in faculty}
    # each course exactly once
    assert sorted(a["course_id"] for a in assignments) == sorted(c["id"] for c in courses)
    for a in assignments:
        key_f = (a["faculty_id"], a["slot_id"])
        key_v = (a["venue_id"], a["slot_id"])
        assert key_f not in slot_of, f"faculty double-booked: {key_f}"
        assert key_v not in venue_of, f"venue double-booked: {key_v}"
        slot_of[key_f] = a["course_id"]
        venue_of[key_v] = a["course_id"]
        assert a["slot_id"] not in fac_unavail.get(a["faculty_id"], set())
        assert a["faculty_id"] == fac_by_course[a["course_id"]]


def test_solver_small_feasible(small_instance):
    faculty, venues, slots, courses = small_instance
    result = TimetableSolver.generate(faculty, venues, slots, courses, time_limit_seconds=5)
    assert result.status in ("optimal", "feasible"), result.status
    assert len(result.assignments) == len(courses)
    assert result.solver_time_ms < 5000
    _assert_no_hard_violations(result.assignments, faculty, venues, slots, courses)


def test_solver_respects_unavailability(small_instance):
    faculty, venues, slots, courses = small_instance
    # Alice unavailable slot 3: her courses must avoid it
    result = TimetableSolver.generate(faculty, venues, slots, courses, time_limit_seconds=5)
    for a in result.assignments:
        if a["faculty_id"] == 1:
            assert a["slot_id"] != 3


def test_solver_infeasible_no_capacity():
    faculty = [{"id": 1, "name": "A", "max_hours_per_day": 6, "max_days_per_week": 5,
                "preferences": [], "unavailable_slots": []}]
    venues = [{"id": 1, "name": "Tiny", "capacity": 10, "equipment": [], "available_slots": []}]
    slots = [{"id": 1, "day_of_week": "Mon", "start_time": "09:00", "end_time": "10:00",
              "duration_minutes": 60}]
    courses = [{"id": 1, "name": "Big", "code": "B1", "faculty_id": 1, "capacity_required": 500,
                "duration_minutes": 60, "required_equipment": []}]
    result = TimetableSolver.generate(faculty, venues, slots, courses, time_limit_seconds=5)
    assert result.status == "infeasible"
    assert result.assignments == []


def test_solver_all_soft_only_still_feasible(small_instance):
    # No unavailability, no preferences: pure feasibility must still solve.
    faculty, venues, slots, courses = small_instance
    for f in faculty:
        f["unavailable_slots"] = []
        f["preferences"] = []
    result = TimetableSolver.generate(faculty, venues, slots, courses, time_limit_seconds=5)
    assert result.status in ("optimal", "feasible")
    assert len(result.assignments) == len(courses)


def _session_instance():
    """One teacher, one 3-session course, two rooms, Mon-Thu mornings."""
    faculty = [{"id": 1, "name": "Alice", "max_hours_per_day": 6, "max_days_per_week": 5,
                "preferences": [], "unavailable_slots": []}]
    venues = [
        {"id": 1, "name": "R1", "capacity": 30, "equipment": [], "available_slots": []},
        {"id": 2, "name": "R2", "capacity": 30, "equipment": [], "available_slots": []},
    ]
    slots = [
        {"id": i + 1, "day_of_week": day, "start_time": "09:00", "end_time": "10:00",
         "duration_minutes": 60}
        for i, day in enumerate(["Mon", "Tue", "Wed", "Thu"])
    ]
    courses = [
        {"id": i + 1, "name": f"Math ({i + 1}/3)", "code": f"M{i + 1}", "faculty_id": 1,
         "capacity_required": 20, "duration_minutes": 60, "required_equipment": []}
        for i in range(3)
    ]
    return faculty, venues, slots, courses


def test_session_group_never_shares_slot():
    faculty, venues, slots, courses = _session_instance()
    groups = [[1, 2, 3]]
    result = TimetableSolver.generate(
        faculty, venues, slots, courses, time_limit_seconds=5, session_groups=groups
    )
    assert result.status in ("optimal", "feasible"), result.status
    assert TimetableSolver.verify(
        result.assignments, courses, faculty, venues, slots, groups
    ) == []
    assert len({a["slot_id"] for a in result.assignments}) == 3


def test_sessions_spread_across_days_fairly():
    """One teacher, 4 sessions, Mon-Fri: no bunched days (fair spread)."""
    faculty = [{"id": 1, "name": "Alice", "max_hours_per_day": 6, "max_days_per_week": 5,
                "preferences": [], "unavailable_slots": []}]
    venues = [{"id": 1, "name": "R1", "capacity": 30, "equipment": [], "available_slots": []}]
    slots = [
        {"id": i + 1, "day_of_week": day, "start_time": "09:00", "end_time": "10:00",
         "duration_minutes": 60}
        for i, day in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri"])
    ]
    courses = [
        {"id": i + 1, "name": f"C{i + 1}", "code": f"C{i + 1}", "faculty_id": 1,
         "capacity_required": 20, "duration_minutes": 60, "required_equipment": []}
        for i in range(4)
    ]
    groups = [[1, 2, 3, 4]]
    result = TimetableSolver.generate(
        faculty, venues, slots, courses, time_limit_seconds=5, session_groups=groups
    )
    assert result.status in ("optimal", "feasible"), result.status
    slot_day = {s["id"]: s["day_of_week"] for s in slots}
    per_day: dict = {}
    for a in result.assignments:
        per_day[slot_day[a["slot_id"]]] = per_day.get(slot_day[a["slot_id"]], 0) + 1
    assert max(per_day.values()) <= 2  # 4 sessions spread, never 3+ on one day
    assert len(per_day) >= 2


def _band_instance():
    """Two teachers, CS-A group courses, morning/afternoon slots."""
    faculty = [
        {"id": 1, "name": "Alice", "max_hours_per_day": 6, "max_days_per_week": 5,
         "preferences": [], "unavailable_slots": []},
        {"id": 2, "name": "Bob", "max_hours_per_day": 6, "max_days_per_week": 5,
         "preferences": [], "unavailable_slots": []},
    ]
    venues = [{"id": 1, "name": "R1", "capacity": 30, "equipment": [], "available_slots": []}]
    slots = [
        {"id": 1, "day_of_week": "Mon", "start_time": "09:00", "end_time": "10:00",
         "duration_minutes": 60},
        {"id": 2, "day_of_week": "Mon", "start_time": "14:00", "end_time": "15:00",
         "duration_minutes": 60},
    ]
    courses = [
        {"id": 1, "name": "Math", "code": "M1", "faculty_id": 1,
         "capacity_required": 20, "duration_minutes": 60, "required_equipment": [],
         "student_group": "CS-A", "preferred_time": "Morning"},
        {"id": 2, "name": "Art", "code": "A1", "faculty_id": 2,
         "capacity_required": 20, "duration_minutes": 60, "required_equipment": [],
         "student_group": "CS-A", "preferred_time": ""},
    ]
    return faculty, venues, slots, courses


def test_student_group_never_overlaps():
    faculty, venues, slots, courses = _band_instance()
    groups = [[1, 2]]  # same student group
    result = TimetableSolver.generate(
        faculty, venues, slots, courses, time_limit_seconds=5, session_groups=groups
    )
    assert result.status in ("optimal", "feasible"), result.status
    assert TimetableSolver.verify(
        result.assignments, courses, faculty, venues, slots, groups
    ) == []
    assert len({a["slot_id"] for a in result.assignments}) == 2


def test_student_group_single_slot_is_infeasible():
    faculty, venues, slots, courses = _band_instance()
    one_slot = [slots[0]]
    result = TimetableSolver.generate(
        faculty, venues, one_slot, courses, time_limit_seconds=5,
        session_groups=[[1, 2]],
    )
    assert result.status == "infeasible"


def test_preferred_time_band_respected():
    faculty, venues, slots, courses = _band_instance()
    morning_only = [courses[0]]  # Math prefers Morning
    result = TimetableSolver.generate(
        faculty, venues, slots, morning_only, time_limit_seconds=5
    )
    assert result.status in ("optimal", "feasible"), result.status
    assert result.assignments[0]["slot_id"] == 1  # 09:00, not 14:00


def _consec_instance():
    faculty = [{"id": 1, "name": "Alice", "max_hours_per_day": 6, "max_days_per_week": 5,
                "preferences": [], "unavailable_slots": []}]
    venues = [{"id": 1, "name": "R1", "capacity": 30, "equipment": [], "available_slots": []}]
    slots = [
        {"id": i + 1, "day_of_week": "Mon", "start_time": f"{9 + i:02d}:00",
         "end_time": f"{10 + i:02d}:00", "duration_minutes": 60}
        for i in range(3)
    ]
    courses = [
        {"id": i + 1, "name": f"C{i + 1}", "code": f"C{i + 1}", "faculty_id": 1,
         "capacity_required": 20, "duration_minutes": 60, "required_equipment": []}
        for i in range(3)
    ]
    return faculty, venues, slots, courses


def test_max_consecutive_break_rule():
    faculty, venues, slots, courses = _consec_instance()
    groups = [[1, 2, 3]]
    # 3 sessions, 3 back-to-back slots, max 2 in a row -> infeasible
    result = TimetableSolver.generate(
        faculty, venues, slots, courses, time_limit_seconds=5,
        session_groups=groups, max_consecutive=2,
    )
    assert result.status == "infeasible"
    # relaxed to 3 -> feasible
    result = TimetableSolver.generate(
        faculty, venues, slots, courses, time_limit_seconds=5,
        session_groups=groups, max_consecutive=3,
    )
    assert result.status in ("optimal", "feasible")
    # off -> feasible
    result = TimetableSolver.generate(
        faculty, venues, slots, courses, time_limit_seconds=5,
        session_groups=groups, max_consecutive=0,
    )
    assert result.status in ("optimal", "feasible")
    # verify flags a 3-run explicitly
    packed = [
        {"course_id": 1, "faculty_id": 1, "venue_id": 1, "slot_id": 1},
        {"course_id": 2, "faculty_id": 1, "venue_id": 1, "slot_id": 2},
        {"course_id": 3, "faculty_id": 1, "venue_id": 1, "slot_id": 3},
    ]
    problems = TimetableSolver.verify(
        packed, courses, faculty, venues, slots, groups, max_consecutive=2
    )
    assert any("back-to-back" in v for v in problems)
