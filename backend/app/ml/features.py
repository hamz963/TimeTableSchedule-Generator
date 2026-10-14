"""Feature engineering: feedback + schedule context -> model rows.

One training row per feedback entry. Features describe the teacher's week in
the schedule they rated (same 6 features are rebuilt at prediction time):

    1. total_minutes        weekly teaching minutes
    2. morning_frac          fraction of sessions starting before 12:00
    3. afternoon_frac        fraction starting 12:00-17:00 (evening = rest)
    4. days_used             distinct teaching days
    5. max_day_minutes       heaviest single-day load
    6. prev_avg_satisfaction teacher's mean satisfaction before this feedback

Label: satisfaction_score (1-5).
"""
from __future__ import annotations

from datetime import time as dtime
from typing import Any, Dict, List, Tuple

FEATURE_NAMES = [
    "total_minutes",
    "morning_frac",
    "afternoon_frac",
    "days_used",
    "max_day_minutes",
    "prev_avg_satisfaction",
]


def _start_minutes(value: Any) -> int:
    if isinstance(value, dtime):
        return value.hour * 60 + value.minute
    try:
        h, m = str(value).split(":")
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return 0


def teacher_schedule_features(
    session_starts: List[Tuple[str, Any]],
    period_minutes: int = 60,
    prev_avg_satisfaction: float = 0.0,
) -> List[float]:
    """session_starts: [(day_of_week, start_time)] for one teacher's week."""
    n = len(session_starts) or 1
    morning = sum(1 for _, st in session_starts if _start_minutes(st) < 12 * 60)
    afternoon = sum(
        1 for _, st in session_starts if 12 * 60 <= _start_minutes(st) < 17 * 60
    )
    per_day: Dict[str, int] = {}
    for day, _ in session_starts:
        per_day[str(day)] = per_day.get(str(day), 0) + period_minutes
    return [
        float(len(session_starts) * period_minutes),
        morning / n,
        afternoon / n,
        float(len(per_day)),
        float(max(per_day.values()) if per_day else 0),
        float(prev_avg_satisfaction),
    ]


def build_training_rows(db) -> Tuple[List[List[float]], List[int], int]:
    """Return (X, y, skipped): one row per usable feedback entry."""
    from app.models.feedback import Feedback
    from app.models.timetable import TimetableEntry
    from app.models.faculty import Faculty
    from app.models.slot import TimeSlot

    feedbacks = db.query(Feedback).order_by(Feedback.id).all()
    if not feedbacks:
        return [], [], 0

    slots = {s.id: s for s in db.query(TimeSlot).all()}
    # teacher name -> id (master rows persisted at generation time)
    name_to_id = {f.name: f.id for f in db.query(Faculty).all()}
    # running satisfaction history per teacher (feedback ordered by id)
    history: Dict[str, List[int]] = {}
    X: List[List[float]] = []
    y: List[int] = []
    skipped = 0

    for fb in feedbacks:
        fid = name_to_id.get(fb.teacher_name)
        entries = (
            db.query(TimetableEntry)
            .filter(
                TimetableEntry.schedule_run_id == fb.schedule_run_id,
                TimetableEntry.faculty_id == fid,
            )
            .all()
            if fid is not None
            else []
        )
        if not entries:
            skipped += 1
            continue
        starts = []
        for e in entries:
            s = slots.get(e.slot_id)
            if s is not None:
                starts.append((s.day_of_week, s.start_time))
        prev = history.get(fb.teacher_name, [])
        prev_avg = sum(prev) / len(prev) if prev else 0.0
        period = 60
        X.append(teacher_schedule_features(starts, period, prev_avg))
        y.append(int(fb.satisfaction_score))
        history.setdefault(fb.teacher_name, []).append(int(fb.satisfaction_score))

    return X, y, skipped
