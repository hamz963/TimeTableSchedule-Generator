"""Interactive edit endpoint tests (shared API client)."""
from tests.shared import get_client

client = get_client()


def _run_id():
    r = client.post("/schedule/generate-simple", json={
        "teachers": [{"name": "Alice"}, {"name": "Bob"}],
        "courses": [
            {"name": "Math", "teacher": "Alice", "credit_hours": 2},
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


def _free_slot(run_id, exclude_own_slot):
    sched = client.get(f"/schedule/{run_id}").json()
    used = {a["slot_id"] for a in sched["assignments"]}
    return next(s["id"] for s in sched["slots"] if s["id"] not in used and s["id"] != exclude_own_slot)


def test_move_valid_creates_new_run():
    rid = _run_id()
    sched = client.get(f"/schedule/{rid}").json()
    first = sched["assignments"][0]
    target = _free_slot(rid, first["slot_id"])
    r = client.post(f"/schedule/{rid}/edit",
                    json={"op": "move", "course_id": first["course_id"], "to_slot_id": target})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["new_run_id"] != rid
    assert body["total_courses_scheduled"] == 3
    assert "move" in body["description"]
    # new run persisted and retrievable; original untouched
    assert len(client.get(f"/schedule/{body['new_run_id']}").json()["assignments"]) == 3
    assert len(client.get(f"/schedule/{rid}").json()["assignments"]) == 3


def test_move_into_conflict_rejected():
    rid = _run_id()
    sched = client.get(f"/schedule/{rid}").json()
    a, b = sched["assignments"][0], sched["assignments"][1]
    # force onto b's slot+room regardless of teachers
    r = client.post(f"/schedule/{rid}/edit", json={
        "op": "move", "course_id": a["course_id"],
        "to_slot_id": b["slot_id"], "to_venue_id": b["venue_id"],
    })
    assert r.status_code == 422
    assert "double-booked" in r.json()["detail"]


def test_move_sibling_onto_same_slot_rejected():
    rid = _run_id()
    sched = client.get(f"/schedule/{rid}").json()
    math_ids = {c["id"] for c in sched["courses"] if c["name"].startswith("Math")}
    math = [a for a in sched["assignments"] if a["course_id"] in math_ids]
    assert len(math) == 2
    a, b = math
    # same teacher already forbids sharing, but the group rule must also fire
    # when rooms differ: move a onto b's slot in the free room if any
    rooms = [rm["id"] for rm in sched["rooms"] if rm["id"] != b["venue_id"]]
    if rooms:
        r = client.post(f"/schedule/{rid}/edit", json={
            "op": "move", "course_id": a["course_id"],
            "to_slot_id": b["slot_id"], "to_venue_id": rooms[0],
        })
        assert r.status_code == 422
        assert "share slot" in r.json()["detail"] or "double-booked" in r.json()["detail"]


def test_swap_and_cancel():
    rid = _run_id()
    sched = client.get(f"/schedule/{rid}").json()
    a, b = sched["assignments"][0], sched["assignments"][-1]
    r = client.post(f"/schedule/{rid}/edit",
                    json={"op": "swap", "course_id_a": a["course_id"], "course_id_b": b["course_id"]})
    if r.status_code == 200:
        assert r.json()["new_run_id"] != rid
    else:  # swap may be infeasible (e.g. sibling clash) — must say why
        assert r.status_code == 422 and r.json()["detail"]

    r = client.post(f"/schedule/{rid}/edit",
                    json={"op": "cancel", "course_id": b["course_id"]})
    assert r.status_code == 200, r.text
    assert r.json()["total_courses_scheduled"] == 2
    assert "cancel" in r.json()["description"]


def test_edit_validates_ids():
    rid = _run_id()
    assert client.post(f"/schedule/{rid}/edit", json={"op": "dance"}).status_code == 422
    assert client.post(f"/schedule/{rid}/edit",
                       json={"op": "cancel", "course_id": 999}).status_code == 422
    assert client.post(f"/schedule/{rid}/edit",
                       json={"op": "move", "course_id": 1, "to_slot_id": 999}).status_code == 422
    assert client.post("/schedule/999999/edit",
                       json={"op": "cancel", "course_id": 1}).status_code == 404
