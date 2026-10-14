"""Interactive timetable editing: move / cancel / swap sessions.

Every edit is validated against the full hard-constraint set (via
solver.verify, including session-group distinctness) and, when clean,
persisted as a NEW schedule run so history is preserved. Used by both the
POST /schedule/{id}/edit endpoint (edit tools UI) and the chatbot.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class EditError(ValueError):
    """Raised when an edit is unknown or would violate hard constraints."""


def _masters(db, run_id: int) -> Dict[str, Any]:
    from app.models.course import Course
    from app.models.faculty import Faculty
    from app.models.slot import TimeSlot
    from app.models.timetable import ScheduleRun, TimetableEntry
    from app.models.venue import Venue

    run = db.get(ScheduleRun, run_id)
    if run is None:
        raise EditError(f"schedule run {run_id} not found")
    entries = (
        db.query(TimetableEntry)
        .filter(TimetableEntry.schedule_run_id == run_id)
        .order_by(TimetableEntry.id)
        .all()
    )
    snap = (run.summary_data or {}).get("masters")
    if snap:
        # Scoped to this dataset (global tables accumulate many datasets).
        faculty, venues, slots, courses = (
            snap["faculty"], snap["venues"], snap["slots"], snap["courses"])
    else:  # legacy runs without a snapshot: fall back to global masters
        from app.models.course import Course
        from app.models.faculty import Faculty
        from app.models.slot import TimeSlot
        from app.models.venue import Venue

        faculty = [
            {"id": f.id, "max_hours_per_day": f.max_hours_per_day,
             "preferences": f.preferences or [], "unavailable_slots": f.unavailable_slots or []}
            for f in db.query(Faculty).all()
        ]
        venues = [
            {"id": v.id, "capacity": v.capacity, "equipment": v.equipment or [],
             "available_slots": v.available_slots or []}
            for v in db.query(Venue).all()
        ]
        slots = [
            {"id": s.id, "day_of_week": s.day_of_week, "duration_minutes": s.duration_minutes}
            for s in db.query(TimeSlot).all()
        ]
        courses = [
            {"id": c.id, "faculty_id": c.faculty_id, "capacity_required": c.capacity_required,
             "required_equipment": c.required_equipment or []}
            for c in db.query(Course).all()
        ]
    return {
        "run": run, "entries": entries, "faculty": faculty, "venues": venues,
        "slots": slots, "courses": courses,
        "session_groups": (run.summary_data or {}).get("session_groups", []),
    }


def describe(op: Dict[str, Any], summary: Optional[Dict[str, Any]] = None) -> str:
    summary = summary or {}
    courses = summary.get("course_labels", {})
    slots = summary.get("slot_labels", {})
    rooms = summary.get("room_names", {})
    course = lambda cid: courses.get(str(cid), f"session {cid}")
    slot = lambda sid: slots.get(str(sid), f"slot {sid}")
    room = lambda vid: rooms.get(str(vid), f"room {vid}")
    kind = op.get("op")
    if kind == "move":
        room_txt = f" in {room(op['to_venue_id'])}" if op.get("to_venue_id") else ""
        return f"move {course(op.get('course_id'))} to {slot(op.get('to_slot_id'))}{room_txt}"
    if kind == "cancel":
        return f"cancel {course(op.get('course_id'))}"
    if kind == "swap":
        return f"swap {course(op.get('course_id_a'))} with {course(op.get('course_id_b'))}"
    return str(op)


def apply_edit(db, run_id: int, op: Dict[str, Any], persist: bool = True) -> Dict[str, Any]:
    """Apply one edit operation; return the new run payload.

    With persist=False (dry run for chat proposals), validates and returns the
    would-be assignments without creating a run.
    """
    from app.models.timetable import ScheduleRun, TimetableEntry
    from app.services.solver import TimetableSolver

    ctx = _masters(db, run_id)
    kind = (op.get("op") or "").lower()
    if kind not in ("move", "cancel", "swap"):
        raise EditError(f"unknown edit '{op.get('op')}'; use move, cancel, or swap")

    assignments = [
        {"course_id": e.course_id, "faculty_id": e.faculty_id,
         "venue_id": e.venue_id, "slot_id": e.slot_id}
        for e in ctx["entries"]
    ]
    by_course = {a["course_id"]: a for a in assignments}
    slot_ids = {s["id"] for s in ctx["slots"]}
    venue_ids = {v["id"] for v in ctx["venues"]}

    if kind == "move":
        cid, sid = op.get("course_id"), op.get("to_slot_id")
        if cid not in by_course:
            raise EditError(f"session {cid} is not in this timetable")
        if sid not in slot_ids:
            raise EditError(f"slot {sid} does not exist")
        vid = op.get("to_venue_id", by_course[cid]["venue_id"])
        if vid not in venue_ids:
            raise EditError(f"room {vid} does not exist")
        by_course[cid]["slot_id"] = sid
        by_course[cid]["venue_id"] = vid
    elif kind == "cancel":
        cid = op.get("course_id")
        if cid not in by_course:
            raise EditError(f"session {cid} is not in this timetable")
        assignments = [a for a in assignments if a["course_id"] != cid]
    else:  # swap
        a_id, b_id = op.get("course_id_a"), op.get("course_id_b")
        if a_id not in by_course or b_id not in by_course:
            raise EditError("both sessions must be in this timetable to swap")
        if a_id == b_id:
            raise EditError("cannot swap a session with itself")
        a, b = by_course[a_id], by_course[b_id]
        a["slot_id"], b["slot_id"] = b["slot_id"], a["slot_id"]
        a["venue_id"], b["venue_id"] = b["venue_id"], a["venue_id"]

    cancelled = {op["course_id"]} if kind == "cancel" else set()
    max_consecutive = int(
        ((ctx["run"].summary_data or {}).get("breaks") or {}).get("max_consecutive_periods", 0)
        or 0
    )
    violations = TimetableSolver.verify(
        assignments, ctx["courses"], ctx["faculty"], ctx["venues"],
        ctx["slots"], ctx["session_groups"], cancelled,
        max_consecutive=max_consecutive,
    )
    if violations:
        raise EditError("edit rejected: " + "; ".join(violations[:4]))

    if not persist:
        return {"new_run_id": None, "assignments": assignments,
                "total_courses_scheduled": len(assignments), "dry_run": True}

    summary = dict(ctx["run"].summary_data or {})
    history = list(summary.get("edits") or [])
    history.append({"op": kind, "detail": op, "at": datetime.now(timezone.utc).isoformat()})
    summary["edits"] = history

    new_run = ScheduleRun(
        completed_at=datetime.now(timezone.utc),
        total_time_ms=0,
        total_courses_scheduled=len(assignments),
        conflicts_resolved=0,
        solver_status="edited",
        summary_data=summary,
    )
    db.add(new_run)
    db.flush()
    for a in assignments:
        db.add(TimetableEntry(
            schedule_run_id=new_run.id, status="completed",
            course_id=a["course_id"], faculty_id=a.get("faculty_id"),
            venue_id=a.get("venue_id"), slot_id=a.get("slot_id"),
            solver_time_ms=0, conflict_count=0,
        ))
    db.commit()
    return {"new_run_id": new_run.id, "assignments": assignments,
            "total_courses_scheduled": len(assignments)}
