"""Auth tests: login, roles, registration, protected routes."""
from fastapi.testclient import TestClient

from tests.shared import app, get_client

authed = get_client()
anon = TestClient(app)  # no Authorization header


def test_login_and_me():
    r = authed.post("/auth/login", json={"username": "admin", "password": "admin"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token_type"] == "bearer" and body["role"] == "admin"

    me = authed.get("/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["username"] == "admin"


def test_login_rejects_bad_password():
    r = anon.post("/auth/login", json={"username": "admin", "password": "wrong"})
    assert r.status_code == 401


def test_protected_routes_need_token():
    assert anon.get("/schedule/1").status_code == 401
    assert anon.get("/constraints").status_code == 401
    assert anon.get("/ml/model-stats").status_code == 401
    assert anon.post("/schedule/generate", json={}).status_code in (401, 422)
    assert anon.get("/health").status_code == 200  # health stays public


def _teacher_client(username="t1"):
    r = authed.post("/auth/register", json={
        "username": username, "password": "secret123", "role": "teacher",
        "teacher_name": "Alice",
    })
    assert r.status_code == 201, r.text
    login = authed.post("/auth/login", json={"username": username, "password": "secret123"})
    token = login.json()["access_token"]
    return TestClient(app, headers={"Authorization": f"Bearer {token}"})


def test_teacher_read_only():
    teacher = _teacher_client("t_readonly")
    # reads allowed
    assert teacher.get("/constraints").status_code == 200
    # writes forbidden
    assert teacher.post("/constraints", json={
        "type": "hard", "name": "x", "description": "", "weight": 1.0,
        "constraint_data": {},
    }).status_code == 403
    assert teacher.post("/schedule/generate", json={}).status_code == 403
    assert teacher.patch("/teachers/1", json={"name": "Z"}).status_code == 403


def test_register_requires_admin_and_validates():
    teacher = _teacher_client("t_reg")
    # non-admin cannot register
    r = teacher.post("/auth/register", json={
        "username": "t_new", "password": "secret123", "role": "teacher",
    })
    assert r.status_code == 403
    # duplicate username rejected
    r = authed.post("/auth/register", json={
        "username": "t_reg", "password": "secret123", "role": "teacher",
    })
    assert r.status_code == 400
    # bad role rejected
    r = authed.post("/auth/register", json={
        "username": "t_badrole", "password": "secret123", "role": "janitor",
    })
    assert r.status_code == 400


def _linked_teacher_client(username, teacher_name):
    r = authed.post("/auth/register", json={
        "username": username, "password": "secret123", "role": "teacher",
        "teacher_name": teacher_name,
    })
    assert r.status_code == 201, r.text
    login = authed.post("/auth/login", json={"username": username, "password": "secret123"})
    return TestClient(app, headers={"Authorization": f"Bearer {login.json()['access_token']}"})


def _scoped_run():
    r = authed.post("/schedule/generate-simple", json={
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


def test_teacher_sees_only_own_schedule():
    rid = _scoped_run()
    alice = _linked_teacher_client("t_alice", "Alice")
    # raw detail + analytics forbidden
    assert alice.get(f"/schedule/{rid}").status_code == 403
    assert alice.get(f"/analytics/schedule/{rid}").status_code == 403
    # other views forbidden
    assert alice.get(f"/schedule/{rid}/views", params={"view": "master"}).status_code == 403
    assert alice.get(f"/export/{rid}", params={"view": "master", "format": "csv"}).status_code == 403
    # own teacher view works and is filtered
    r = alice.get(f"/schedule/{rid}/views", params={"view": "teacher"})
    assert r.status_code == 200, r.text
    assert [t["name"] for t in r.json()["teachers"]] == ["Alice"]
    # own export works
    r = alice.get(f"/export/{rid}", params={"view": "teacher", "format": "csv"})
    assert r.status_code == 200 and b"Alice" in r.content
    # edits forbidden
    assert alice.post(f"/schedule/{rid}/edit",
                      json={"op": "cancel", "course_id": 1}).status_code == 403


def test_teacher_without_link_is_blocked():
    rid = _scoped_run()
    loner = _linked_teacher_client("t_loner", "")
    # empty teacher_name treated as unlinked
    r = loner.get(f"/schedule/{rid}/views", params={"view": "teacher"})
    assert r.status_code == 403


def test_teacher_chat_cannot_edit():
    from app.services import chat as chat_service
    chat_service.clear_conversations()
    rid = _scoped_run()
    alice = _linked_teacher_client("t_chat", "Alice")
    cid = alice.post("/chat/start", json={"schedule_run_id": rid}).json()["conversation_id"]
    m = alice.post(f"/chat/{cid}/message", json={"message": "cancel Art"}).json()
    assert "can't change timetables" in m["reply"]
    # but export flow still offers their own schedule
    m = alice.post(f"/chat/{cid}/message",
                   json={"message": "my teacher schedule as pdf"}).json()
    assert "teacher" in m["selected_views"]
    g = alice.post(f"/chat/{cid}/generate", json={"formats": ["csv"]})
    assert g.status_code == 200
    assert list(g.json()["views"]) == ["teacher"]


def test_runs_list_endpoint():
    rid = _scoped_run()
    r = authed.get("/schedule/runs")
    assert r.status_code == 200
    assert any(x["schedule_run_id"] == rid for x in r.json())
