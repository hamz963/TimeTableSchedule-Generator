"""API integration tests (SQLite-backed, no Postgres needed)."""
from tests.shared import (  # noqa: F401
    TestingSession, app, engine, get_client, override_db,
)
from tests.conftest import make_small_instance

client = get_client()


def setup_module():
    pass  # tables created by tests.shared at import


def _gen_payload():
    faculty, venues, slots, courses = make_small_instance()
    return {
        "faculty": [
            {"id": f["id"], "name": f["name"], "max_hours_per_day": f["max_hours_per_day"],
             "max_days_per_week": f["max_days_per_week"], "preferences": f["preferences"],
             "unavailable_slots": f["unavailable_slots"]}
            for f in faculty
        ],
        "venues": [
            {"id": v["id"], "name": v["name"], "capacity": v["capacity"],
             "equipment": v["equipment"], "available_slots": v["available_slots"]}
            for v in venues
        ],
        "slots": [
            {"id": s["id"], "day_of_week": s["day_of_week"], "start_time": s["start_time"],
             "end_time": s["end_time"], "duration_minutes": s["duration_minutes"]}
            for s in slots
        ],
        "courses": [
            {"id": c["id"], "name": c["name"], "code": c["code"], "faculty_id": c["faculty_id"],
             "capacity_required": c["capacity_required"], "duration_minutes": c["duration_minutes"],
             "required_equipment": c["required_equipment"]}
            for c in courses
        ],
    }


def test_generate_end_to_end():
    r = client.post("/schedule/generate", json=_gen_payload())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_courses_scheduled"] == 3
    run_id = body["schedule_run_id"]

    r2 = client.get(f"/schedule/{run_id}")
    assert r2.status_code == 200
    assert len(r2.json()["assignments"]) == 3

    r3 = client.get(f"/analytics/schedule/{run_id}")
    assert r3.status_code == 200
    assert "preference_satisfaction_pct" in r3.json()


def test_generate_invalid_returns_400():
    payload = _gen_payload()
    payload["courses"] = []
    r = client.post("/schedule/generate", json=payload)
    assert r.status_code in (400, 422)


def test_constraint_crud():
    r = client.post("/constraints", json={
        "type": "hard", "name": "no-overlap", "description": "no double booking",
        "weight": 1.0, "constraint_data": {},
    })
    assert r.status_code == 201, r.text
    cid = r.json()["id"]

    r = client.get("/constraints")
    assert r.status_code == 200 and any(c["id"] == cid for c in r.json())

    r = client.delete(f"/constraints/{cid}")
    assert r.status_code == 204

    r = client.get(f"/constraints/{cid}")
    assert r.status_code == 404


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def _simple_payload():
    return {
        "teachers": [{"name": "Alice"}, {"name": "Bob", "unavailable_days": ["Fri"]}],
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


def test_generate_simple_end_to_end():
    r = client.post("/schedule/generate-simple", json=_simple_payload())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_courses_scheduled"] == 4  # 3 + 1 sessions
    assert body["summary"]["sessions"] == 4
    assert body["summary"]["rooms_auto"] is True
    run_id = body["schedule_run_id"]

    r2 = client.get(f"/schedule/{run_id}")
    assert r2.status_code == 200
    assert len(r2.json()["assignments"]) == 4


def test_generate_simple_rejects_unknown_teacher():
    payload = _simple_payload()
    payload["courses"] = [{"name": "X", "teacher": "Nobody", "credit_hours": 2}]
    r = client.post("/schedule/generate-simple", json=payload)
    assert r.status_code == 400, r.text
    assert "unknown teacher" in r.json()["detail"]


def test_generate_simple_rejects_bad_time_format():
    payload = _simple_payload()
    payload["day_start"] = "8am"
    r = client.post("/schedule/generate-simple", json=payload)
    assert r.status_code == 422  # pydantic schema validation
