"""Real-time events + quality/explainability API tests."""
import asyncio

from app.services.events import broker, reset
from tests.shared import get_client  # noqa: F401 (sets up app + auth)

client = get_client()


def test_broker_publish_subscribe_roundtrip():
    reset()

    async def scenario():
        agen = broker.subscribe(replay=0)
        pending = asyncio.ensure_future(agen.__anext__())
        await asyncio.sleep(0)  # let the subscriber register its queue
        broker.publish({"type": "schedule.created", "run_id": 42})
        event = await asyncio.wait_for(pending, timeout=2)
        await agen.aclose()
        return event

    event = asyncio.run(scenario())
    assert event["type"] == "schedule.created"
    assert event["run_id"] == 42
    assert broker.recent(10)[-1]["run_id"] == 42


def _simple_payload():
    return {
        "teachers": [{"name": "A"}, {"name": "B"}],
        "courses": [
            {"name": "Math", "teacher": "A", "credit_hours": 2, "preferred_time": "Morning"},
            {"name": "Art", "teacher": "B", "credit_hours": 1},
        ],
        "rooms": [], "days": ["Mon", "Tue", "Wed", "Thu", "Fri"],
        "day_start": "08:00", "day_end": "15:00", "period_minutes": 60,
        "gap_minutes": 10, "lunch_break": True, "lunch_start": "12:00", "lunch_end": "13:00",
    }


def test_generate_returns_quality_and_engine_and_emits_event():
    reset()
    r = client.post("/schedule/generate-simple", json=_simple_payload())
    assert r.status_code == 200, r.text
    body = r.json()
    assert "quality" in body and body["quality"]["score"]["score"] >= 0
    assert body["engine"]["path"] in ("exact", "heuristic", "greedy-fallback")
    types = [e["type"] for e in client.get("/events/recent").json()["events"]]
    assert "schedule.created" in types


def test_quality_endpoint_for_stored_run():
    r = client.post("/schedule/generate-simple", json=_simple_payload())
    run_id = r.json()["schedule_run_id"]
    r = client.get(f"/quality/{run_id}")
    assert r.status_code == 200, r.text
    data = r.json()
    assert 0 <= data["quality"]["score"]["score"] <= 100
    assert data["quality"]["teachers"]


def test_quality_endpoint_404_for_missing_run():
    assert client.get("/quality/999999").status_code == 404


def test_benchmark_reports_optimizer_value():
    r = client.post("/quality/benchmark", json={
        "n_faculty": 50, "n_rooms": 20, "n_courses": 100, "n_slots": 40,
        "optimize_seconds": 0.5,
    })
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["feasible"] is True
    assert b["optimized_cost"] <= b["greedy_cost"]
    assert b["hard_violations_after_optimize"] == []
    assert b["optimized_quality"] >= b["greedy_quality"] - 1e-9


def test_events_status_and_recent_require_auth():
    assert client.get("/events/status").status_code == 200
    assert client.get("/events/recent").status_code == 200


def test_persisted_constraint_drives_generation():
    """A stored Constraint row (not just an inline rule) must reach the solver."""
    created = client.post("/constraints", json={
        "type": "hard", "name": "no-same-day", "description": "", "weight": 1.0,
        "constraint_data": {"kind": "no_same_day",
                            "params": {"course_a": "Math", "course_b": "Art"}},
    })
    assert created.status_code == 201, created.text
    cid = created.json()["id"]
    try:
        r = client.post("/schedule/generate-simple", json=_simple_payload())
        assert r.status_code == 200, r.text
        body = r.json()
        labels = body["summary"]["slot_labels"]
        clabels = body["summary"]["course_labels"]
        math_days = {labels[str(a["slot_id"])][:3] for a in body["assignments"]
                     if clabels[str(a["course_id"])].startswith("Math")}
        art_days = {labels[str(a["slot_id"])][:3] for a in body["assignments"]
                    if clabels[str(a["course_id"])] == "Art"}
        assert math_days.isdisjoint(art_days), (math_days, art_days)
    finally:
        assert client.delete(f"/constraints/{cid}").status_code == 204
