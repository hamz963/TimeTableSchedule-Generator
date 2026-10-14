"""Celery task tests (eager execution — no broker required)."""
from app.tasks import solve_timetable_task
from tests.conftest import make_small_instance


def _payload():
    faculty, venues, slots, courses = make_small_instance()
    return {
        "faculty": faculty,
        "venues": venues,
        "slots": slots,
        "courses": courses,
        "time_limit_seconds": 5,
    }


def test_task_solves_small_instance():
    result = solve_timetable_task.apply(args=(_payload(),)).get()
    assert result["status"] in ("optimal", "feasible")
    assert result["total_courses_scheduled"] == 3
    assert len(result["assignments"]) == 3


def test_task_rejects_invalid_payload():
    payload = _payload()
    payload["courses"] = []
    result = solve_timetable_task.apply(args=(payload,)).get()
    assert result["status"] == "invalid"
    assert result["assignments"] == []
