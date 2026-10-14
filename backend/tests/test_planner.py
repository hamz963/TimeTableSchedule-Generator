"""Planner tests: slot grid with breaks, credit-hour expansion, auto rooms."""
import pytest
from app.services.planner import build_problem, normalize_day
from app.services.validator import ValidationError


def _base(**overrides):
    payload = {
        "teachers": [{"name": "Alice"}, {"name": "Bob"}],
        "courses": [
            {"name": "Math", "teacher": "Alice", "credit_hours": 3},
            {"name": "Art", "teacher": "Bob", "credit_hours": 1},
        ],
        "rooms": [],
        "days": ["Mon", "Tue", "Wed", "Thu", "Fri"],
        "day_start": "08:00",
        "day_end": "15:00",
        "period_minutes": 60,
        "gap_minutes": 10,
        "lunch_break": True,
        "lunch_start": "12:00",
        "lunch_end": "13:00",
    }
    payload.update(overrides)
    return payload


def test_slot_grid_skips_lunch_and_keeps_gaps():
    p = build_problem(_base())
    # 08:00, 09:10, 10:20, (11:30 skipped: touches lunch), 13:50 -> 4/day
    assert p["summary"]["slots_per_day"] == {d: 4 for d in ["Mon", "Tue", "Wed", "Thu", "Fri"]}
    for s in p["slots"]:
        assert not (s["start_time"] < "13:00" and s["end_time"] > "12:00"), s
    # 10-minute gaps between consecutive periods
    monday = [s for s in p["slots"] if s["day_of_week"] == "Mon"]
    assert [s["start_time"] for s in monday] == ["08:00", "09:10", "10:20", "13:50"]


def test_no_lunch_break_gives_continuous_grid():
    p = build_problem(_base(lunch_break=False))
    monday = [s["start_time"] for s in p["slots"] if s["day_of_week"] == "Mon"]
    assert monday == ["08:00", "09:10", "10:20", "11:30", "12:40", "13:50"]


def test_credit_hours_expand_to_sessions_with_groups():
    p = build_problem(_base())
    assert len(p["courses"]) == 4  # 3 + 1 sessions
    assert p["session_groups"] == [[1, 2, 3]]  # only multi-session course grouped
    assert p["summary"]["sessions"] == 4


def test_rooms_auto_created_with_capacity():
    p = build_problem(_base())
    assert len(p["venues"]) >= 1
    assert p["summary"]["rooms_auto"] is True
    need = max(c["capacity_required"] for c in p["courses"])
    assert all(v["capacity"] >= need for v in p["venues"])


def test_unavailable_days_map_to_slots():
    p = build_problem(_base(teachers=[
        {"name": "Alice", "unavailable_days": ["Friday"]},
        {"name": "Bob"},
    ]))
    alice = p["faculty"][0]
    friday_slots = [s["id"] for s in p["slots"] if s["day_of_week"] == "Fri"]
    assert set(alice["unavailable_slots"]) == set(friday_slots)


def test_day_names_normalized():
    assert normalize_day("monday") == "Mon"
    assert normalize_day("FRI") == "Fri"
    p = build_problem(_base(days=["monday", "tuesday"]))
    assert p["summary"]["days"] == ["Mon", "Tue"]


def test_unknown_teacher_rejected():
    with pytest.raises(ValidationError, match="unknown teacher"):
        build_problem(_base(courses=[{"name": "X", "teacher": "Nobody", "credit_hours": 1}]))


def test_bad_window_rejected():
    with pytest.raises(ValidationError, match="day_end must be after day_start"):
        build_problem(_base(day_start="15:00", day_end="08:00"))


def test_duplicate_teachers_rejected():
    with pytest.raises(ValidationError, match="unique"):
        build_problem(_base(teachers=[{"name": "Al"}, {"name": "Al"}]))


def test_too_few_rooms_rejected_with_actionable_message():
    with pytest.raises(ValidationError, match="extend"):
        build_problem(
            _base(
                rooms=[{"name": "Only"}],
                days=["Mon"],
                day_start="08:00",
                day_end="09:00",  # 1 slot x 1 room < 4 sessions
            )
        )


def test_duplicate_teacher_course_rejected():
    payload = _base(courses=[
        {"name": "Math", "teacher": "Alice", "credit_hours": 1},
        {"name": "Math", "teacher": "Alice", "credit_hours": 1},
    ])
    with pytest.raises(ValidationError, match="Duplicate"):
        build_problem(payload)


def test_teacher_overload_rejected_with_hours():
    payload = _base(
        teachers=[{"name": "Alice"}],
        courses=[{"name": "Math", "teacher": "Alice", "credit_hours": 4}],
        days=["Mon"],
        day_start="08:00",
        day_end="09:00",  # 1 slot = 60 free minutes, needs 240
    )
    with pytest.raises(ValidationError, match="needs .* but only .* free"):
        build_problem(payload)


def test_student_groups_clustered():
    payload = _base(courses=[
        {"name": "Math", "teacher": "Alice", "credit_hours": 2, "student_group": "CS-A"},
        {"name": "Art", "teacher": "Bob", "credit_hours": 1, "student_group": "CS-A"},
    ])
    p = build_problem(payload)
    assert p["summary"]["student_groups"] == ["CS-A"]
    assert [1, 2] in p["session_groups"]  # multi-session course
    assert [1, 2, 3] in p["session_groups"]  # whole student group


def test_bad_preferred_time_rejected():
    payload = _base(courses=[
        {"name": "Math", "teacher": "Alice", "credit_hours": 1, "preferred_time": "Midnight"},
    ])
    with pytest.raises(ValidationError, match="preferred_time"):
        build_problem(payload)
