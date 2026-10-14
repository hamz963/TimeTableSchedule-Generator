"""Multi-view generation: one timetable, perspectives per audience.

Views: master (day x room grid), teacher (per-teacher week), student
(per-course meetings), staff (per-slot occupancy + breaks), canteen
(lunch window + per-slot demand proxy + peaks).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

DAY_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

VIEWS = ["master", "teacher", "student", "staff", "canteen"]


def _label(mapping: Dict[str, str], key: int, prefix: str) -> str:
    return mapping.get(str(key), f"{prefix} {key}")


def get_run_context(db, run_id: int) -> Dict[str, Any]:
    """Load entries + names/labels for a run (graceful when summary missing)."""
    from app.models.course import Course
    from app.models.faculty import Faculty
    from app.models.slot import TimeSlot
    from app.models.timetable import ScheduleRun, TimetableEntry
    from app.models.venue import Venue

    run = db.get(ScheduleRun, run_id)
    if run is None:
        raise KeyError(f"schedule run {run_id} not found")
    entries = (
        db.query(TimetableEntry)
        .filter(TimetableEntry.schedule_run_id == run_id)
        .order_by(TimetableEntry.id)
        .all()
    )
    summary = run.summary_data or {}
    courses = {c.id: c for c in db.query(Course).all()}
    faculty = {f.id: f for f in db.query(Faculty).all()}
    venues = {v.id: v for v in db.query(Venue).all()}
    slots = {s.id: s for s in db.query(TimeSlot).all()}

    course_labels = dict(summary.get("course_labels", {}))
    slot_labels = dict(summary.get("slot_labels", {}))
    teacher_names = dict(summary.get("teacher_names", {}))
    room_names = dict(summary.get("room_names", {}))
    for e in entries:
        course_labels.setdefault(str(e.course_id), getattr(courses.get(e.course_id), "name", f"Course {e.course_id}"))
        if e.faculty_id is not None:
            teacher_names.setdefault(str(e.faculty_id), getattr(faculty.get(e.faculty_id), "name", f"Teacher {e.faculty_id}"))
        if e.venue_id is not None:
            room_names.setdefault(str(e.venue_id), getattr(venues.get(e.venue_id), "name", f"Room {e.venue_id}"))
        s = slots.get(e.slot_id)
        if s is not None:
            slot_labels.setdefault(
                str(e.slot_id),
                f"{s.day_of_week} {s.start_time:%H:%M}-{s.end_time:%H:%M}"
                if hasattr(s.start_time, "strftime") else f"{s.day_of_week} {s.start_time}-{s.end_time}",
            )

    days = list(summary.get("days", [])) or sorted(
        {getattr(slots.get(e.slot_id), "day_of_week", "?") for e in entries},
        key=lambda d: DAY_ORDER.index(d) if d in DAY_ORDER else 99,
    )

    def slot_sort(e):
        s = slots.get(e.slot_id)
        if s is None:
            return (99, "")
        day_i = DAY_ORDER.index(s.day_of_week) if s.day_of_week in DAY_ORDER else 99
        return (day_i, str(s.start_time))

    return {
        "run": run,
        "entries": sorted(entries, key=slot_sort),
        "summary": summary,
        "days": days,
        "slots": slots,
        "course_labels": course_labels,
        "slot_labels": slot_labels,
        "teacher_names": teacher_names,
        "room_names": room_names,
    }


def run_metrics(db, run_id: int) -> Dict[str, Any]:
    """Satisfaction/fairness metrics for exports and panels."""
    from app.models.faculty import Faculty

    ctx = get_run_context(db, run_id)
    prefs = {f.id: set(f.preferences or []) for f in db.query(Faculty).all()}
    hits = sum(
        1 for e in ctx["entries"] if e.slot_id in prefs.get(e.faculty_id, set())
    )
    total = len(ctx["entries"]) or 1
    teachers = {e.faculty_id for e in ctx["entries"] if e.faculty_id is not None}
    return {
        "total_sessions": len(ctx["entries"]),
        "total_teachers": len(teachers),
        "preference_satisfaction": round(hits / total, 4),
        "solver_status": ctx["run"].solver_status,
        "solver_time_ms": ctx["run"].total_time_ms,
        "lunch_break": (ctx["summary"].get("breaks") or {}).get("lunch_break"),
    }


def master_table(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Grid rows x rooms table shared by exports."""
    venue_ids = sorted({e.venue_id for e in ctx["entries"] if e.venue_id is not None})
    headers = ["Time"] + [_label(ctx["room_names"], v, "Room") for v in venue_ids]
    by_slot: Dict[int, Dict[int, Any]] = {}
    for e in ctx["entries"]:
        by_slot.setdefault(e.slot_id, {})[e.venue_id] = e
    rows = []
    seen_slots = sorted(
        by_slot,
        key=lambda sid: (
            DAY_ORDER.index(ctx["slots"][sid].day_of_week)
            if sid in ctx["slots"] and ctx["slots"][sid].day_of_week in DAY_ORDER
            else 99,
            str(getattr(ctx["slots"].get(sid), "start_time", "")),
        ),
    )
    for sid in seen_slots:
        row = [_label(ctx["slot_labels"], sid, "Slot")]
        for vid in venue_ids:
            e = by_slot[sid].get(vid)
            if e is None:
                row.append("—")
            else:
                row.append(
                    f"{_label(ctx['course_labels'], e.course_id, 'Course')}\n"
                    f"{_label(ctx['teacher_names'], e.faculty_id or 0, 'Teacher')}"
                )
        rows.append(row)
    return {"title": "Master Timetable", "headers": headers, "rows": rows}


def build_view(db, run_id: int, view: str, teacher_only: Optional[str] = None) -> Dict[str, Any]:
    """Build one audience view (JSON-serializable).

    teacher_only: when set with view='teacher', keep only that teacher's entry.
    """
    if view not in VIEWS:
        raise ValueError(f"unknown view '{view}'; choose from {VIEWS}")
    ctx = get_run_context(db, run_id)
    entries = ctx["entries"]

    def session(e) -> Dict[str, Any]:
        return {
            "course": _label(ctx["course_labels"], e.course_id, "Course"),
            "teacher": _label(ctx["teacher_names"], e.faculty_id or 0, "Teacher"),
            "room": _label(ctx["room_names"], e.venue_id or 0, "Room"),
            "slot": _label(ctx["slot_labels"], e.slot_id, "Slot"),
            "slot_id": e.slot_id,
        }

    if view == "master":
        table = master_table(ctx)
        return {"view": "master", "days": ctx["days"], **table,
                "lunch_break": (ctx["summary"].get("breaks") or {}).get("lunch_break")}

    if view == "teacher":
        by_teacher: Dict[str, List[Dict[str, Any]]] = {}
        for e in entries:
            t = _label(ctx["teacher_names"], e.faculty_id or 0, "Teacher")
            s = session(e)
            by_teacher.setdefault(t, []).append(
                {"day_slot": s["slot"], "course": s["course"], "room": s["room"]}
            )
        teachers = [{"name": t, "sessions": s} for t, s in sorted(by_teacher.items())]
        if teacher_only is not None:
            teachers = [t for t in teachers if t["name"] == teacher_only]
        return {"view": "teacher", "teachers": teachers}

    if view == "student":
        import re as _re

        by_course: Dict[str, Dict[str, Any]] = {}
        for e in entries:
            full = _label(ctx["course_labels"], e.course_id, "Course")
            base = _re.sub(r"\s*\(\d+/\d+\)$", "", full)  # "Math (1/3)" -> "Math"
            s = session(e)
            grp = by_course.setdefault(base, {"course": base, "teacher": s["teacher"], "sessions": []})
            grp["sessions"].append({"meeting": full, "day_slot": s["slot"], "room": s["room"]})
        return {"view": "student", "courses": sorted(by_course.values(), key=lambda g: g["course"])}

    # staff + canteen need per-slot concurrency
    by_slot: Dict[int, List[Any]] = {}
    for e in entries:
        by_slot.setdefault(e.slot_id, []).append(e)
    venue_ids = {e.venue_id for e in entries if e.venue_id is not None}
    slot_rows = []
    for sid, es in sorted(by_slot.items()):
        slot_rows.append(
            {
                "slot": _label(ctx["slot_labels"], sid, "Slot"),
                "concurrent_classes": len(es),
                "teachers_busy": sorted(
                    {_label(ctx["teacher_names"], e.faculty_id or 0, "Teacher") for e in es}
                ),
                "rooms_in_use": sorted(
                    {_label(ctx["room_names"], e.venue_id or 0, "Room") for e in es}
                ),
                "free_rooms": max(0, len(venue_ids) - len({e.venue_id for e in es})),
            }
        )

    if view == "staff":
        return {"view": "staff", "days": ctx["days"], "slots": slot_rows,
                "lunch_break": (ctx["summary"].get("breaks") or {}).get("lunch_break")}

    # canteen: lunch window + demand proxy (concurrency) + peaks
    peaks = sorted(slot_rows, key=lambda r: r["concurrent_classes"], reverse=True)[:3]
    return {
        "view": "canteen",
        "lunch_window": (ctx["summary"].get("breaks") or {}).get("lunch_break"),
        "note": "Demand proxy = concurrent classes that release students toward breaks/lunch.",
        "slots": [
            {"slot": r["slot"], "concurrent_classes": r["concurrent_classes"]}
            for r in slot_rows
        ],
        "peak_slots": [p["slot"] for p in peaks],
    }
