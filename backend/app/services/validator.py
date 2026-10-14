"""Constraint validation for schedule generation requests."""
from __future__ import annotations

from typing import Any, Dict, List


class ValidationError(ValueError):
    pass


class PayloadTooLargeError(ValidationError):
    """Oversized request (DoS protection); endpoints map this to HTTP 413."""
    pass


# DoS guardrails: generous for real schools, fatal for abuse. Estimated model
# variables (courses x venues x slots) drive CP-SAT build cost (~45 us/var).
MAX_FACULTY = 1000
MAX_VENUES = 500
MAX_SLOTS = 2000
MAX_COURSES = 5000
MAX_EST_VARS = 2_000_000


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise ValidationError(msg)


def _require_size(cond: bool, msg: str) -> None:
    if not cond:
        raise PayloadTooLargeError(msg)


def validate_generate_request(payload: Dict[str, Any]) -> None:
    """Validate raw dict payload (faculty/venues/slots/courses). Raises ValidationError."""
    faculty: List[Dict[str, Any]] = payload.get("faculty", [])
    venues: List[Dict[str, Any]] = payload.get("venues", [])
    slots: List[Dict[str, Any]] = payload.get("slots", [])
    courses: List[Dict[str, Any]] = payload.get("courses", [])

    _require(isinstance(faculty, list) and faculty, "faculty list must be non-empty")
    _require(isinstance(venues, list) and venues, "venues list must be non-empty")
    _require(isinstance(slots, list) and slots, "slots list must be non-empty")
    _require(isinstance(courses, list) and courses, "courses list must be non-empty")

    faculty_ids = {f.get("id") for f in faculty}
    slot_ids = {s.get("id") for s in slots}
    venue_ids = {v.get("id") for v in venues}

    _require(len(faculty_ids) == len(faculty), "duplicate faculty ids")
    _require(len(slot_ids) == len(slots), "duplicate slot ids")
    _require(len(venue_ids) == len(venues), "duplicate venue ids")
    _require(None not in faculty_ids, "faculty entries must have ids")
    _require(None not in slot_ids, "slot entries must have ids")
    _require(None not in venue_ids, "venue entries must have ids")

    _require_size(len(faculty) <= MAX_FACULTY, f"too many faculty (max {MAX_FACULTY})")
    _require_size(len(venues) <= MAX_VENUES, f"too many venues (max {MAX_VENUES})")
    _require_size(len(slots) <= MAX_SLOTS, f"too many slots (max {MAX_SLOTS})")
    _require_size(len(courses) <= MAX_COURSES, f"too many courses (max {MAX_COURSES})")
    _require_size(
        len(courses) * len(venues) * len(slots) <= MAX_EST_VARS,
        f"problem too large (max {MAX_EST_VARS} course x venue x slot combinations); "
        "split into smaller batches",
    )

    for v in venues:
        _require(int(v.get("capacity", 0)) > 0, f"venue {v.get('id')} capacity must be > 0")

    for f in faculty:
        for sid in f.get("unavailable_slots", []) or []:
            _require(sid in slot_ids, f"faculty {f.get('id')} unavailable slot {sid} unknown")
        _require(int(f.get("max_hours_per_day", 6)) >= 1, "max_hours_per_day must be >= 1")

    for c in courses:
        _require(c.get("faculty_id") in faculty_ids, f"course {c.get('id')} references unknown faculty")
        _require(int(c.get("capacity_required", 0)) > 0, f"course {c.get('id')} capacity must be > 0")
        # At least one venue big enough with matching equipment must exist.
        capable = [
            v for v in venues
            if int(v.get("capacity", 0)) >= int(c.get("capacity_required", 0))
            and set(c.get("required_equipment", []) or []).issubset(set(v.get("equipment", []) or []))
        ]
        _require(bool(capable), f"course {c.get('id')}: no venue satisfies capacity/equipment")

    # Slot sanity: start < end when parseable "HH:MM".
    for s in slots:
        try:
            sh, sm = map(int, str(s.get("start_time", "09:00")).split(":"))
            eh, em = map(int, str(s.get("end_time", "10:00")).split(":"))
        except (ValueError, AttributeError):
            continue  # non parseable times are tolerated (DB Time type enforced at persistence)
        _require((eh * 60 + em) > (sh * 60 + sm), f"slot {s.get('id')} end must be after start")
