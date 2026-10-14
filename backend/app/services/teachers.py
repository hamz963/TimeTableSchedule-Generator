"""Teacher service: rename with propagation into run summaries.

Shared by the PATCH /teachers endpoint and the chatbot.
"""
from __future__ import annotations

import copy
from typing import Any, Dict


class TeacherNotFoundError(ValueError):
    pass


class BadTeacherNameError(ValueError):
    pass


def rename_teacher(db, faculty_id: int, name: str) -> Dict[str, Any]:
    """Rename a teacher; propagate into every stored run summary. Returns stats."""
    from app.models.faculty import Faculty
    from app.models.timetable import ScheduleRun

    teacher = db.get(Faculty, faculty_id)
    if teacher is None:
        raise TeacherNotFoundError(f"teacher {faculty_id} not found")
    name = (name or "").strip()
    if not name:
        raise BadTeacherNameError("teacher name must not be blank")
    old_name = teacher.name
    teacher.name = name

    # NOTE: deep-copy first — mutating the live nested dict would also mutate
    # SQLAlchemy's committed-state reference and the write would be skipped.
    runs_updated = 0
    for run in db.query(ScheduleRun).all():
        summary = copy.deepcopy(run.summary_data or {})
        names = summary.get("teacher_names")
        if isinstance(names, dict) and str(faculty_id) in names:
            names[str(faculty_id)] = name
            run.summary_data = summary
            runs_updated += 1

    # Keep ML history intact: feedback references teachers by name.
    from app.models.feedback import Feedback

    feedback_updated = (
        db.query(Feedback)
        .filter(Feedback.teacher_name == old_name)
        .update({"teacher_name": name}, synchronize_session=False)
    )
    db.commit()
    return {"id": teacher.id, "name": name, "runs_updated": runs_updated,
            "feedback_updated": feedback_updated}
