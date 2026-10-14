"""Feedback + ML endpoint tests (shared API client)."""
from tests.shared import get_client

client = get_client()


def _simple_run(teachers=("Alice", "Bob")):
    payload = {
        "teachers": [{"name": t} for t in teachers],
        "courses": [
            {"name": "Math", "teacher": teachers[0], "credit_hours": 2},
            {"name": "Art", "teacher": teachers[1], "credit_hours": 1},
        ],
        "rooms": [],
        "days": ["Mon", "Tue"],
        "day_start": "08:00",
        "day_end": "12:00",
        "period_minutes": 60,
        "gap_minutes": 10,
        "lunch_break": False,
    }
    r = client.post("/schedule/generate-simple", json=payload)
    assert r.status_code == 200, r.text
    return r.json()["schedule_run_id"]


def test_feedback_crud_and_listing():
    run_id = _simple_run()
    r = client.post("/feedback", json={
        "schedule_run_id": run_id,
        "teacher_name": "Alice",
        "satisfaction_score": 5,
        "preferred_time": "Morning",
        "workload_satisfaction": 4,
        "comments": "Great mornings!",
    })
    assert r.status_code == 201, r.text
    assert r.json()["teacher_name"] == "Alice"

    r2 = client.get(f"/feedback/schedule/{run_id}")
    assert r2.status_code == 200
    assert any(f["teacher_name"] == "Alice" for f in r2.json())


def test_feedback_rejects_unknown_run():
    r = client.post("/feedback", json={
        "schedule_run_id": 999999, "teacher_name": "Ghost", "satisfaction_score": 3,
    })
    assert r.status_code == 404


def test_feedback_rejects_bad_time_and_score():
    run_id = _simple_run()
    r = client.post("/feedback", json={
        "schedule_run_id": run_id, "teacher_name": "Alice",
        "satisfaction_score": 5, "preferred_time": "Midnight",
    })
    assert r.status_code == 400
    r = client.post("/feedback", json={
        "schedule_run_id": run_id, "teacher_name": "Alice", "satisfaction_score": 9,
    })
    assert r.status_code == 422  # pydantic range validation


def test_ml_stats_shape():
    r = client.get("/ml/model-stats")
    assert r.status_code == 200
    body = r.json()
    for key in ("model_version", "training_samples", "model_accuracy",
                "feedback_count", "next_retrain"):
        assert key in body


def test_retrain_and_suggest_flow(tmp_path, monkeypatch):
    import app.ml.learner as learner

    monkeypatch.setattr(learner, "MODEL_DIR", tmp_path)
    monkeypatch.setattr(learner, "MODEL_PATH", tmp_path / "preference_model.pkl")
    monkeypatch.setattr(learner, "SCALER_PATH", tmp_path / "scaler.pkl")

    run_id = _simple_run()
    # one consistent signal: mornings make Alice happy (25 rows)
    for score in ([5] * 12 + [4] * 13):
        r = client.post("/feedback", json={
            "schedule_run_id": run_id, "teacher_name": "Alice",
            "satisfaction_score": score, "preferred_time": "Morning",
            "workload_satisfaction": 4,
        })
        assert r.status_code == 201
    for _ in range(5):
        r = client.post("/feedback", json={
            "schedule_run_id": run_id, "teacher_name": "Bob",
            "satisfaction_score": 2, "preferred_time": "Morning",
            "workload_satisfaction": 2,
        })
        assert r.status_code == 201

    tr = client.post("/ml/retrain")
    assert tr.status_code == 200, tr.text
    assert tr.json()["trained"] is True

    sg = client.post("/ml/suggest", json={
        "teacher_name": "Alice",
        "total_minutes": 180,
        "slots": [
            {"id": 1, "day_of_week": "Mon", "start_time": "09:00"},
            {"id": 2, "day_of_week": "Mon", "start_time": "14:00"},
        ],
    })
    assert sg.status_code == 200, sg.text
    assert sg.json()["suggestion"]["slot_ids"] == [1]


def test_suggest_without_model_is_503(tmp_path, monkeypatch):
    import app.ml.learner as learner

    monkeypatch.setattr(learner, "MODEL_PATH", tmp_path / "m.pkl")
    monkeypatch.setattr(learner, "SCALER_PATH", tmp_path / "s.pkl")
    r = client.post("/ml/suggest", json={"teacher_name": "Nobody", "total_minutes": 60})
    assert r.status_code == 503
