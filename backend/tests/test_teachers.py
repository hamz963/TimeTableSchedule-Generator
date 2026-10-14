"""Teacher rename tests (shared API client)."""
from tests.shared import get_client

client = get_client()


def _run_id():
    r = client.post("/schedule/generate-simple", json={
        "teachers": [{"name": "Alice"}, {"name": "Bob"}],
        "courses": [
            {"name": "Math", "teacher": "Alice", "credit_hours": 1},
            {"name": "Art", "teacher": "Bob", "credit_hours": 1},
        ],
        "rooms": [],
        "days": ["Mon", "Tue"],
        "day_start": "08:00",
        "day_end": "12:00",
        "period_minutes": 60,
        "gap_minutes": 10,
        "lunch_break": False,
    })
    assert r.status_code == 200, r.text
    return r.json()["schedule_run_id"]


def _fid(run_id, name):
    sched = client.get(f"/schedule/{run_id}").json()
    return next(t["id"] for t in sched["teachers"] if t["name"] == name)


def test_rename_propagates_to_views():
    rid = _run_id()
    fid = _fid(rid, "Alice")
    r = client.patch(f"/teachers/{fid}", json={"name": "Alicia"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == fid and body["name"] == "Alicia" and body["runs_updated"] == 1

    names = [t["name"] for t in
             client.get(f"/schedule/{rid}/views", params={"view": "teacher"}).json()["teachers"]]
    assert "Alicia" in names and "Alice" not in names
    # schedule pickers + master labels follow too
    assert any(t["name"] == "Alicia" for t in client.get(f"/schedule/{rid}").json()["teachers"])


def test_rename_validates():
    rid = _run_id()
    fid = _fid(rid, "Bob")
    assert client.patch("/teachers/999999", json={"name": "X"}).status_code == 404
    assert client.patch(f"/teachers/{fid}", json={"name": "   "}).status_code == 400
    assert client.patch(f"/teachers/{fid}", json={"name": ""}).status_code == 422


def test_rename_keeps_feedback_history():
    rid = _run_id()
    fid = _fid(rid, "Alice")
    assert client.post("/feedback", json={
        "schedule_run_id": rid, "teacher_name": "Alice", "satisfaction_score": 5,
    }).status_code == 201
    body = client.patch(f"/teachers/{fid}", json={"name": "Alicia"}).json()
    assert body["feedback_updated"] == 1
    names = [f["teacher_name"] for f in client.get(f"/feedback/schedule/{rid}").json()]
    assert names == ["Alicia"]
