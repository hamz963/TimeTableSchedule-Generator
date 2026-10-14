"""ML unit tests: features, training, prediction (isolated model dir)."""
import pytest

from app.ml.features import FEATURE_NAMES, build_training_rows, teacher_schedule_features


@pytest.fixture
def db_session():
    """Private in-memory DB per test (no cross-test interference)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app.database import Base

    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    Base.metadata.create_all(bind=eng)
    db = sessionmaker(bind=eng)()
    yield db
    db.close()


def test_feature_vector_shape_and_values():
    starts = [("Mon", "09:00"), ("Mon", "10:00"), ("Tue", "14:00")]
    vec = teacher_schedule_features(starts, period_minutes=60, prev_avg_satisfaction=4.0)
    assert len(vec) == len(FEATURE_NAMES) == 6
    assert vec[0] == 180.0  # total minutes
    assert vec[1] == pytest.approx(2 / 3)  # morning frac
    assert vec[2] == pytest.approx(1 / 3)  # afternoon frac
    assert vec[3] == 2.0  # days used
    assert vec[4] == 120.0  # max day minutes
    assert vec[5] == 4.0


def _seed_db(db, run_id=1):
    """Two teachers, morning vs afternoon weeks, opposing satisfaction."""
    from datetime import time
    from app.models.course import Course
    from app.models.faculty import Faculty
    from app.models.feedback import Feedback
    from app.models.slot import TimeSlot
    from app.models.timetable import ScheduleRun, TimetableEntry

    db.add_all([
        Faculty(id=1, name="Alice", max_hours_per_day=6, max_days_per_week=5),
        Faculty(id=2, name="Bob", max_hours_per_day=6, max_days_per_week=5),
        TimeSlot(id=1, day_of_week="Mon", start_time=time(9, 0), end_time=time(10, 0)),
        TimeSlot(id=2, day_of_week="Mon", start_time=time(14, 0), end_time=time(15, 0)),
        Course(id=1, name="M", code="M1", faculty_id=1),
        Course(id=2, name="P", code="P1", faculty_id=2),
        ScheduleRun(id=run_id, solver_status="optimal"),
    ])
    db.flush()
    # Alice: morning sessions, happy; Bob: afternoon sessions, unhappy
    # (15 + 15 = 30 rows: the minimum the product spec requires to train)
    for i in range(15):
        db.add(TimetableEntry(schedule_run_id=run_id, course_id=1, faculty_id=1,
                              venue_id=1, slot_id=1))
        db.add(Feedback(schedule_run_id=run_id, teacher_name="Alice",
                        satisfaction_score=5, preferred_time="Morning",
                        workload_satisfaction=5))
    for i in range(15):
        db.add(TimetableEntry(schedule_run_id=run_id, course_id=2, faculty_id=2,
                              venue_id=1, slot_id=2))
        db.add(Feedback(schedule_run_id=run_id, teacher_name="Bob",
                        satisfaction_score=2, preferred_time="Morning",
                        workload_satisfaction=2))
    db.commit()


def test_build_training_rows(db_session):
    _seed_db(db_session)
    X, y, skipped = build_training_rows(db_session)
    assert len(X) == 30 and len(y) == 30 and skipped == 0
    assert set(y) == {5, 2}
    assert all(len(row) == 6 for row in X)


def test_train_and_suggest(tmp_path, monkeypatch, db_session):
    import app.ml.learner as learner

    monkeypatch.setattr(learner, "MODEL_DIR", tmp_path)
    monkeypatch.setattr(learner, "MODEL_PATH", tmp_path / "preference_model.pkl")
    monkeypatch.setattr(learner, "SCALER_PATH", tmp_path / "scaler.pkl")
    _seed_db(db_session)

    stats = learner.train_model(db_session)
    assert stats["trained"] is True
    assert stats["samples"] == 30
    assert (tmp_path / "preference_model.pkl").exists()

    from app.ml.predictor import suggest_preferences

    slots = [
        {"id": 1, "day_of_week": "Mon", "start_time": "09:00"},
        {"id": 2, "day_of_week": "Mon", "start_time": "14:00"},
    ]
    alice = suggest_preferences(db_session, "Alice", slots, total_minutes=240)
    assert alice is not None
    assert alice["time_of_day"] == "Morning"
    assert alice["slot_ids"] == [1]
    bob = suggest_preferences(db_session, "Bob", slots, total_minutes=240)
    assert bob is not None
    # Bob rated afternoons 2/5 and prefers mornings -> model steers him to mornings too
    assert bob["slot_ids"] == [1]


def test_suggest_without_model_returns_none(db_session, tmp_path, monkeypatch):
    import app.ml.learner as learner

    monkeypatch.setattr(learner, "MODEL_PATH", tmp_path / "m.pkl")
    monkeypatch.setattr(learner, "SCALER_PATH", tmp_path / "s.pkl")
    from app.ml.predictor import suggest_preferences

    assert suggest_preferences(db_session, "Nobody", [], 60) is None


def test_train_refuses_tiny_data(db_session, tmp_path, monkeypatch):
    import app.ml.learner as learner

    monkeypatch.setattr(learner, "MODEL_DIR", tmp_path)
    monkeypatch.setattr(learner, "MODEL_PATH", tmp_path / "m.pkl")
    monkeypatch.setattr(learner, "SCALER_PATH", tmp_path / "s.pkl")
    stats = learner.train_model(db_session)
    assert stats["trained"] is False
    assert "at least" in stats["reason"]
