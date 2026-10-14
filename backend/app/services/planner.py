"""Teacher-friendly planner: simple dataset -> solver-ready problem.

The teacher provides only:
    teachers: names (+ optional daily limit, unavailable days)
    courses:   name, teacher name, credit hours (= weekly sessions)
    rooms:     optional (auto-created when omitted)
    day window: start/end time, period length, gap between periods, lunch break

The planner expands this into faculty/venues/slots/session-courses plus
session groups (a course's weekly sessions must not share a slot) and a
human-readable summary with display labels for the frontend.
"""
from __future__ import annotations

from typing import Any, Dict, List

from app.services.validator import PayloadTooLargeError, ValidationError

_DAY_ALIASES = {
    "mon": "Mon", "monday": "Mon",
    "tue": "Tue", "tues": "Tue", "tuesday": "Tue",
    "wed": "Wed", "wednesday": "Wed",
    "thu": "Thu", "thur": "Thu", "thurs": "Thu", "thursday": "Thu",
    "fri": "Fri", "friday": "Fri",
    "sat": "Sat", "saturday": "Sat",
    "sun": "Sun", "sunday": "Sun",
}


def normalize_day(value: str) -> str:
    """Accept 'Mon', 'monday', 'MON' ... -> canonical 'Mon'."""
    key = (value or "").strip().lower()
    if key not in _DAY_ALIASES:
        raise ValidationError(
            f"unknown day '{value}'; use Mon/Tue/Wed/Thu/Fri/Sat/Sun (full names ok)"
        )
    return _DAY_ALIASES[key]


def parse_hhmm(value: str) -> int:
    """'HH:MM' -> minutes since midnight."""
    try:
        h, m = value.split(":")
        minutes = int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        raise ValidationError(f"invalid time '{value}'; expected HH:MM")
    if not (0 <= int(h) <= 23 and 0 <= int(m) <= 59):
        raise ValidationError(f"invalid time '{value}'; expected HH:MM")
    return minutes


def fmt_hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def build_problem(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Expand a SimpleGenerateRequest dict into solver inputs + summary."""
    teachers = payload.get("teachers", [])
    courses_in = payload.get("courses", [])
    rooms_in = payload.get("rooms", []) or []
    raw_days = payload.get("days", ["Mon", "Tue", "Wed", "Thu", "Fri"])
    if not raw_days:
        raise ValidationError("days must list at least one day (e.g. Mon..Fri)")

    days = [normalize_day(d) for d in raw_days]
    if len(set(days)) != len(days):
        raise ValidationError("days contains duplicates")

    names = [t.get("name", "").strip() for t in teachers]
    if any(not n for n in names):
        raise ValidationError("every teacher needs a name")
    if len(set(names)) != len(names):
        raise ValidationError("teacher names must be unique")
    if len(teachers) > 1000:
        raise PayloadTooLargeError("too many teachers (max 1000)")
    teacher_id = {n: i + 1 for i, n in enumerate(names)}

    seen_pairs = set()
    for c in courses_in:
        tname = (c.get("teacher") or "").strip()
        if tname not in teacher_id:
            raise ValidationError(
                f"course '{c.get('name')}' references unknown teacher '{c.get('teacher')}'"
            )
        if not (c.get("name") or "").strip():
            raise ValidationError("Course name is missing")
        pair = (tname, c["name"].strip())
        if pair in seen_pairs:
            raise ValidationError(
                f"Duplicate: teacher '{tname}' already teaches '{c['name'].strip()}'"
            )
        seen_pairs.add(pair)

    start = parse_hhmm(payload.get("day_start", "08:00"))
    end = parse_hhmm(payload.get("day_end", "15:00"))
    if end <= start:
        raise ValidationError("day_end must be after day_start")
    period = int(payload.get("period_minutes", 60))
    gap = int(payload.get("gap_minutes", 10))
    lunch = bool(payload.get("lunch_break", True))
    lunch_s = parse_hhmm(payload.get("lunch_start", "12:00"))
    lunch_e = parse_hhmm(payload.get("lunch_end", "13:00"))
    if lunch and lunch_e <= lunch_s:
        raise ValidationError("lunch_end must be after lunch_start")

    # --- time slots: stride the day, skip anything touching lunch ------------
    slots: List[Dict[str, Any]] = []
    slot_id = 1
    for day in days:
        t = start
        while t + period <= end:
            s, e = t, t + period
            overlaps_lunch = lunch and s < lunch_e and e > lunch_s
            if not overlaps_lunch:
                slots.append(
                    {
                        "id": slot_id,
                        "day_of_week": day,
                        "start_time": fmt_hhmm(s),
                        "end_time": fmt_hhmm(e),
                        "duration_minutes": period,
                        "label": f"{day} {fmt_hhmm(s)}–{fmt_hhmm(e)}",
                    }
                )
                slot_id += 1
            t += period + gap
    if not slots:
        raise ValidationError(
            "no class periods fit in the given day window; "
            "extend day_start/day_end or shorten period_minutes"
        )
    day_slot_ids: Dict[str, List[int]] = {}
    for s in slots:
        day_slot_ids.setdefault(s["day_of_week"], []).append(s["id"])

    # --- faculty ---------------------------------------------------------------
    faculty = []
    for t in teachers:
        unav_days = [normalize_day(d) for d in t.get("unavailable_days", []) or []]
        unav_slots = [sid for d in unav_days for sid in day_slot_ids.get(d, [])]
        faculty.append(
            {
                "id": teacher_id[t["name"].strip()],
                "name": t["name"].strip(),
                "max_hours_per_day": int(t.get("max_hours_per_day", 6)),
                "max_days_per_week": 7,
                "preferences": [],
                "unavailable_slots": unav_slots,
            }
        )

    # --- load pre-check: "Teacher X needs N hours but only M are free" --------
    need_min: Dict[str, int] = {}
    for c in courses_in:
        tname = c["teacher"].strip()
        need_min[tname] = need_min.get(tname, 0) + int(c.get("credit_hours", 1)) * period
    for f in faculty:
        free_min = (len(slots) - len(f.get("unavailable_slots", []))) * period
        if need_min.get(f["name"], 0) > free_min:
            def _h(m: int) -> str:
                return f"{m / 60:g} hours" if m % 60 == 0 else f"{m} minutes"

            raise ValidationError(
                f"Teacher '{f['name']}' needs {_h(need_min[f['name']])} "
                f"but only {_h(free_min)} are free; extend the day, add days, "
                "free up unavailable days, or reduce credit hours"
            )

    # --- session expansion: 1 credit hour = 1 weekly session -------------------
    courses: List[Dict[str, Any]] = []
    session_groups: List[List[int]] = []
    course_labels: Dict[int, str] = {}
    cid = 1
    for c in courses_in:
        n = int(c.get("credit_hours", 1))
        group_name = (c.get("student_group") or "").strip()
        band = (c.get("preferred_time") or "").strip().capitalize()
        if band not in ("", "Morning", "Afternoon", "Evening"):
            raise ValidationError(
                f"course '{c.get('name')}': preferred_time must be Morning, "
                "Afternoon, Evening, or blank"
            )
        group = []
        for i in range(1, n + 1):
            label = f"{c['name']} ({i}/{n})" if n > 1 else c["name"]
            courses.append(
                {
                    "id": cid,
                    "name": label,
                    "code": f"AUTO-{cid:04d}",
                    "faculty_id": teacher_id[c["teacher"].strip()],
                    "capacity_required": int(c.get("capacity_required", 30)),
                    "duration_minutes": period,
                    "required_equipment": c.get("required_equipment", []) or [],
                    "student_group": group_name,
                    "preferred_time": band,
                }
            )
            course_labels[cid] = label
            group.append(cid)
            cid += 1
        if len(group) > 1:
            session_groups.append(group)
    # Student groups: all sessions of one group never meet simultaneously.
    by_group: Dict[str, List[int]] = {}
    for c in courses:
        if c.get("student_group"):
            by_group.setdefault(c["student_group"], []).append(c["id"])
    for members in by_group.values():
        if len(members) > 1:
            session_groups.append(sorted(members))
    total_sessions = len(courses)
    if total_sessions > 5000:
        raise PayloadTooLargeError(
            "too many sessions (max 5000); split into smaller batches"
        )

    # --- rooms (auto when omitted) ---------------------------------------------
    venues = []
    if rooms_in:
        if len(rooms_in) > 500:
            raise PayloadTooLargeError("too many rooms (max 500)")
        for i, r in enumerate(rooms_in, start=1):
            if not (r.get("name") or "").strip():
                raise ValidationError("every room needs a name")
            venues.append(
                {
                    "id": i,
                    "name": r["name"].strip(),
                    "capacity": int(r.get("capacity", 30)),
                    "equipment": [],
                    "available_slots": [],
                }
            )
    else:
        # Default 5 rooms (Room 1 to Room 5); extend via rooms if insufficient.
        for i in range(1, 6):
            venues.append(
                {
                    "id": i,
                    "name": f"Room {i}",
                    "capacity": max(c["capacity_required"] for c in courses),
                    "equipment": [],
                    "available_slots": [],
                }
            )
    if len(venues) * len(slots) < total_sessions:
        raise ValidationError(
            f"only {len(venues) * len(slots)} class meetings fit in "
            f"{len(venues)} room(s) x {len(slots)} time slot(s), but "
            f"{total_sessions} sessions are needed; add rooms or extend hours"
        )

    summary = {
        "teachers": len(faculty),
        "courses": len(courses_in),
        "sessions": total_sessions,
        "session_groups": session_groups,
        "student_groups": sorted(by_group),
        "days": days,
        "slots_per_day": {d: len(day_slot_ids.get(d, [])) for d in days},
        "total_slots": len(slots),
        "rooms": [v["name"] for v in venues],
        "rooms_auto": not bool(rooms_in),
        "breaks": {
            "gap_minutes_between_periods": gap,
            "lunch_break": (
                f"{fmt_hhmm(lunch_s)}–{fmt_hhmm(lunch_e)}" if lunch else None
            ),
            "max_consecutive_periods": int(payload.get("max_consecutive_periods", 2)),
        },
        "fairness": [
            "multi-session courses never share a time slot",
            "no student group has two classes at once",
            "sessions spread across different days when possible",
            "teaching load spread evenly across days (no bunched days)",
            "lunch break is free for everyone",
        ],
        "course_labels": {str(k): v for k, v in course_labels.items()},
        "slot_labels": {str(s["id"]): s["label"] for s in slots},
        "teacher_names": {str(f["id"]): f["name"] for f in faculty},
        "room_names": {str(v["id"]): v["name"] for v in venues},
        # Full master snapshot so later edits/verify see exactly this dataset
        # (global master tables accumulate many datasets over time).
        "masters": {
            "faculty": faculty,
            "venues": venues,
            "slots": slots,
            "courses": courses,
        },
    }
    return {
        "faculty": faculty,
        "venues": venues,
        "slots": slots,
        "courses": courses,
        "session_groups": session_groups,
        "summary": summary,
    }


ID_BLOCK = 100_000


def next_id_block(db) -> int:
    """First free 100k id block across all master tables (per-dataset ids)."""
    from sqlalchemy import func as _func
    from app.models.course import Course
    from app.models.faculty import Faculty
    from app.models.slot import TimeSlot
    from app.models.venue import Venue

    peak = 0
    for model in (Faculty, Venue, TimeSlot, Course):
        peak = max(peak, db.query(_func.coalesce(_func.max(model.id), 0)).scalar() or 0)
    return (peak // ID_BLOCK + 1) * ID_BLOCK


def build_id_maps(faculty, venues, slots, courses, base: int):
    """Old id -> rebased id for each entity kind."""
    return (
        {f["id"]: f["id"] + base for f in faculty},
        {v["id"]: v["id"] + base for v in venues},
        {s["id"]: s["id"] + base for s in slots},
        {c["id"]: c["id"] + base for c in courses},
    )


def rebase_ids(problem: Dict[str, Any], base: int) -> Dict[str, Any]:
    """Shift every id in a built problem by `base` (server-owned id space).

    Each generate-simple dataset gets a fresh id block, so master rows merged
    into the global tables can never collide with (or corrupt) other datasets'
    runs. All internal references and summary label maps are remapped.
    """
    if not base:
        return problem
    fid, vid, sid, cid = build_id_maps(
        problem["faculty"], problem["venues"], problem["slots"], problem["courses"], base
    )

    for f in problem["faculty"]:
        f["id"] = fid[f["id"]]
        f["unavailable_slots"] = [sid[s] for s in f.get("unavailable_slots", [])]
    for v in problem["venues"]:
        v["id"] = vid[v["id"]]
        avail = v.get("available_slots") or []
        v["available_slots"] = [sid[s] for s in avail]
    for s in problem["slots"]:
        s["id"] = sid[s["id"]]
    for c in problem["courses"]:
        c["id"] = cid[c["id"]]
        c["faculty_id"] = fid[c["faculty_id"]]
        c["code"] = f"AUTO-{c['id']:06d}"  # unique per dataset (ids are rebased)
    problem["session_groups"] = [[cid[i] for i in g] for g in problem["session_groups"]]

    summary = problem.get("summary", {})
    for key, mapping in (("course_labels", cid), ("slot_labels", sid),
                         ("teacher_names", fid), ("room_names", vid)):
        if isinstance(summary.get(key), dict):
            summary[key] = {str(mapping[int(k)]): v for k, v in summary[key].items()}
    return problem


def summarize_advanced(faculty, venues, slots, courses) -> Dict[str, Any]:
    """Build a display summary + master snapshot for advanced (JSON) payloads.

    Gives advanced runs the same self-contained summary that planner-built
    runs get: human labels for views/exports/chat, and scoped masters for
    later edits and analytics.
    """
    days = sorted({str(s.get("day_of_week", "?")) for s in slots})
    summary = {
        "source": "advanced",
        "teachers": len(faculty),
        "courses": len(courses),
        "sessions": len(courses),
        "session_groups": [],
        "days": days,
        "slots_per_day": {},
        "total_slots": len(slots),
        "rooms": [v.get("name", "") for v in venues],
        "rooms_auto": False,
        "course_labels": {str(c["id"]): c.get("name", "") for c in courses},
        "slot_labels": {
            str(s["id"]): f"{s.get('day_of_week', '?')} {s.get('start_time', '')}–{s.get('end_time', '')}"
            for s in slots
        },
        "teacher_names": {str(f["id"]): f.get("name", "") for f in faculty},
        "room_names": {str(v["id"]): v.get("name", "") for v in venues},
        "masters": {
            "faculty": faculty,
            "venues": venues,
            "slots": slots,
            "courses": courses,
        },
    }
    for s in slots:
        day = str(s.get("day_of_week", "?"))
        summary["slots_per_day"][day] = summary["slots_per_day"].get(day, 0) + 1
    return summary
