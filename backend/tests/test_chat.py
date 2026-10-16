"""Chat conversation tests (shared API client)."""
from app.services import chat as chat_service
from tests.shared import get_client

client = get_client()


def _run_id():
    r = client.post("/schedule/generate-simple", json={
        "teachers": [{"name": "Alice"}],
        "courses": [{"name": "Math", "teacher": "Alice", "credit_hours": 1}],
        "rooms": [],
        "days": ["Mon"],
        "day_start": "08:00",
        "day_end": "10:00",
        "period_minutes": 60,
        "gap_minutes": 10,
        "lunch_break": False,
    })
    assert r.status_code == 200, r.text
    return r.json()["schedule_run_id"]


def _start(run_id=None):
    r = client.post("/chat/start", json={"schedule_run_id": run_id})
    assert r.status_code == 200
    return r.json()["conversation_id"]


def test_chat_full_flow_to_ready():
    chat_service.clear_conversations()
    cid = _start(_run_id())
    m1 = client.post(f"/chat/{cid}/message",
                     json={"message": "I need schedules for teachers and canteen staff"}).json()
    assert m1["status"] == "collecting"
    assert "teacher" in m1["selected_views"] and "canteen" in m1["selected_views"]
    m2 = client.post(f"/chat/{cid}/message",
                     json={"message": "PDF and Excel please"}).json()
    assert m2["status"] == "collecting"  # still wants the morning/afternoon question
    assert set(m2["selected_formats"]) == {"pdf", "xlsx"}
    m3 = client.post(f"/chat/{cid}/message", json={"message": "morning"}).json()
    assert m3["status"] == "ready_to_generate"

    g = client.post(f"/chat/{cid}/generate", json={})
    assert g.status_code == 200, g.text
    body = g.json()
    assert body["schedules_generated"] == 3 * 2  # 3 views x 2 formats
    assert set(body["views"]) == {"teacher", "staff", "canteen"}
    assert set(body["views"]["teacher"]) == {"pdf", "xlsx"}
    assert body["views"]["teacher"]["pdf"].startswith("/export/")


def test_chat_help_and_unknown_conversation():
    chat_service.clear_conversations()
    cid = _start()
    m = client.post(f"/chat/{cid}/message", json={"message": "help"}).json()
    assert "teacher" in m["reply"].lower()
    assert client.post("/chat/nope123/message", json={"message": "hi"}).status_code == 404
    assert client.post("/chat/nope123/generate", json={}).status_code == 404


def test_chat_generate_needs_schedule_attached():
    chat_service.clear_conversations()
    cid = _start()  # no run attached
    client.post(f"/chat/{cid}/message", json={"message": "teacher schedules as pdf"}).json()
    client.post(f"/chat/{cid}/message", json={"message": "morning"}).json()
    g = client.post(f"/chat/{cid}/generate", json={})
    assert g.status_code == 400


def test_chat_generate_overrides():
    chat_service.clear_conversations()
    cid = _start(_run_id())
    g = client.post(f"/chat/{cid}/generate",
                    json={"views": ["master"], "formats": ["json"]})
    assert g.status_code == 200
    assert g.json()["schedules_generated"] == 1


def _edit_run():
    r = client.post("/schedule/generate-simple", json={
        "teachers": [{"name": "Alice"}, {"name": "Bob"}],
        "courses": [
            {"name": "Math", "teacher": "Alice", "credit_hours": 2},
            {"name": "Art", "teacher": "Bob", "credit_hours": 1},
        ],
        "rooms": [],
        "days": ["Mon", "Tue", "Wed"],
        "day_start": "08:00",
        "day_end": "13:00",
        "period_minutes": 60,
        "gap_minutes": 10,
        "lunch_break": False,
    })
    assert r.status_code == 200, r.text
    return r.json()["schedule_run_id"]


def test_chat_move_propose_confirm_apply():
    from app.services import chat as chat_service
    chat_service.clear_conversations()
    rid = _edit_run()
    cid = client.post("/chat/start", json={"schedule_run_id": rid}).json()["conversation_id"]
    m = client.post(f"/chat/{cid}/message",
                    json={"message": "move Math (1/2) to Wednesday"}).json()
    assert m["status"] == "confirm_edit", m
    assert m.get("pending_edit")
    m2 = client.post(f"/chat/{cid}/message", json={"message": "yes"}).json()
    assert m2["status"] == "edit_applied", m2
    assert m2["new_run_id"] != rid
    assert len(client.get(f"/schedule/{m2['new_run_id']}").json()["assignments"]) == 3


def test_chat_move_ambiguous_session_asks_which():
    from app.services import chat as chat_service
    chat_service.clear_conversations()
    rid = _edit_run()
    cid = client.post("/chat/start", json={"schedule_run_id": rid}).json()["conversation_id"]
    m = client.post(f"/chat/{cid}/message", json={"message": "move Math to Friday"}).json()
    assert m["status"] == "collecting"
    assert "Math (1/2)" in m["reply"] and "Math (2/2)" in m["reply"]


def test_chat_cancel_and_dismiss():
    from app.services import chat as chat_service
    chat_service.clear_conversations()
    rid = _edit_run()
    cid = client.post("/chat/start", json={"schedule_run_id": rid}).json()["conversation_id"]
    m = client.post(f"/chat/{cid}/message", json={"message": "cancel Art"}).json()
    assert m["status"] == "confirm_edit"
    m2 = client.post(f"/chat/{cid}/message", json={"message": "no, forget it"}).json()
    assert m2["status"] == "collecting"
    assert len(client.get(f"/schedule/{rid}").json()["assignments"]) == 3  # untouched


def test_chat_edit_unknown_session_explains():
    from app.services import chat as chat_service
    chat_service.clear_conversations()
    rid = _edit_run()
    cid = client.post("/chat/start", json={"schedule_run_id": rid}).json()["conversation_id"]
    m = client.post(f"/chat/{cid}/message", json={"message": "move Potions to Tuesday"}).json()
    assert m["status"] == "collecting"
    assert "Which session" in m["reply"]


def test_chat_rename_teacher_applies_immediately():
    from app.services import chat as chat_service
    chat_service.clear_conversations()
    rid = _edit_run()
    cid = client.post("/chat/start", json={"schedule_run_id": rid}).json()["conversation_id"]
    m = client.post(f"/chat/{cid}/message",
                    json={"message": "rename Alice to Alicia"}).json()
    assert m["status"] == "collecting", m
    assert "Alicia" in m["reply"]
    names = [t["name"] for t in
             client.get(f"/schedule/{rid}/views", params={"view": "teacher"}).json()["teachers"]]
    assert "Alicia" in names


def test_chat_rename_unknown_teacher_lists_names():
    from app.services import chat as chat_service
    chat_service.clear_conversations()
    rid = _edit_run()
    cid = client.post("/chat/start", json={"schedule_run_id": rid}).json()["conversation_id"]
    m = client.post(f"/chat/{cid}/message",
                    json={"message": "rename Severus to Snape"}).json()
    assert "don't see a teacher" in m["reply"]
