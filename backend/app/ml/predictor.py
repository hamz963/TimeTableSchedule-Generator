"""Predict time-of-day preferences for teachers from the trained model.

Probes three archetype weeks (morning-heavy / balanced / afternoon-heavy) with
the teacher's real load, picks the pattern with the highest expected
satisfaction, and maps it to concrete slot ids for the solver.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional


def _model_available() -> bool:
    from app.ml.learner import MODEL_PATH, SCALER_PATH

    return MODEL_PATH.exists() and SCALER_PATH.exists()


def _slots_in_bucket(slots: List[Dict[str, Any]], bucket: str) -> List[int]:
    out = []
    for s in slots:
        try:
            h, m = str(s.get("start_time", "09:00")).split(":")
            start = int(h) * 60 + int(m)
        except (ValueError, AttributeError):
            continue
        if bucket == "Morning" and start < 12 * 60:
            out.append(s["id"])
        elif bucket == "Afternoon" and 12 * 60 <= start < 17 * 60:
            out.append(s["id"])
        elif bucket == "Evening" and start >= 17 * 60:
            out.append(s["id"])
    return out


def suggest_preferences(
    db,
    teacher_name: str,
    slots: List[Dict[str, Any]],
    total_minutes: int,
    period_minutes: int = 60,
) -> Optional[Dict[str, Any]]:
    """Return {time_of_day, slot_ids, confidence, expected_satisfaction} or None."""
    if not _model_available():
        return None
    import joblib
    import numpy as np

    from app.ml.learner import MODEL_PATH, SCALER_PATH
    from app.models.feedback import Feedback

    model = joblib.load(MODEL_PATH)
    scaler = joblib.load(SCALER_PATH)

    sessions = max(1, int(round(total_minutes / max(period_minutes, 1))))
    days_available = len({s.get("day_of_week") for s in slots}) or 1
    days_used = min(days_available, sessions)
    max_day = math.ceil(sessions / days_used) * period_minutes

    prev = [
        r[0]
        for r in db.query(Feedback.satisfaction_score)
        .filter(Feedback.teacher_name == teacher_name)
        .all()
    ]
    prev_avg = sum(prev) / len(prev) if prev else 0.0

    patterns = {
        "Morning": (0.8, 0.2),
        "Balanced": (0.5, 0.5),
        "Afternoon": (0.2, 0.8),
    }
    classes = list(model.classes_)
    best = None
    for pattern, (morn, aft) in patterns.items():
        vec = scaler.transform(
            [[total_minutes, morn, aft, days_used, max_day, prev_avg]]
        )
        proba = model.predict_proba(vec)[0]
        expected = float(np.dot(proba, classes))
        if best is None or expected > best[1]:
            best = (pattern, expected, float(np.max(proba)))
    pattern, expected, confidence = best
    bucket = "Morning" if pattern == "Morning" else "Afternoon" if pattern == "Afternoon" else ""
    slot_ids = _slots_in_bucket(slots, bucket) if bucket else []
    if not slot_ids:  # balanced or empty bucket: no slot restriction
        return {
            "time_of_day": pattern,
            "slot_ids": [],
            "confidence": round(confidence, 3),
            "expected_satisfaction": round(expected, 3),
        }
    return {
        "time_of_day": bucket,
        "slot_ids": slot_ids,
        "confidence": round(confidence, 3),
        "expected_satisfaction": round(expected, 3),
    }
