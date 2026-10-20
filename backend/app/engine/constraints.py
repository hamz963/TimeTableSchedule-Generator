"""Hard-constraint verification.

Returns a list of human-readable violation messages (empty == compliant).
Message strings are part of the public contract: the edit tools, chatbot and
test-suite assert on them, so they are kept byte-for-byte stable while the
check now also audits declarative user rules.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.engine.context import ProblemContext, build_context

Map = Dict[int, Tuple[int, int]]


def to_map(assignments: Iterable[Dict[str, int]]) -> Map:
    return {a["course_id"]: (a["venue_id"], a["slot_id"]) for a in assignments}


def verify(
    assignments: List[Dict[str, int]],
    courses: List[Dict[str, Any]],
    faculty: List[Dict[str, Any]],
    venues: List[Dict[str, Any]],
    slots: List[Dict[str, Any]],
    session_groups: Optional[List[List[int]]] = None,
    cancelled: Optional[set] = None,
    max_consecutive: int = 0,
    ctx: Optional[ProblemContext] = None,
) -> List[str]:
    """Check all hard constraints; return violation messages (empty = ok)."""
    if ctx is None:
        ctx = build_context(faculty, venues, slots, courses,
                            session_groups=session_groups, max_consecutive=max_consecutive)

    violations: List[str] = []
    course_by_id = dict(ctx.course_by_id)
    if cancelled:
        course_by_id = {cid: c for cid, c in course_by_id.items() if cid not in cancelled}

    if sorted(a["course_id"] for a in assignments) != sorted(course_by_id):
        violations.append("each course must be assigned exactly once")

    fac_slot: set = set()
    ven_slot: set = set()
    day_mins: Dict[Tuple[int, str], int] = {}
    for a in assignments:
        c = course_by_id.get(a["course_id"], {})
        if a["faculty_id"] != c.get("faculty_id"):
            violations.append(f"course {a['course_id']}: wrong faculty")
        k1 = (a["faculty_id"], a["slot_id"])
        k2 = (a["venue_id"], a["slot_id"])
        if k1 in fac_slot:
            violations.append(f"faculty double-booked: {k1}")
        if k2 in ven_slot:
            violations.append(f"venue double-booked: {k2}")
        fac_slot.add(k1)
        ven_slot.add(k2)

        f = ctx.faculty_by_id.get(a["faculty_id"], {})
        if a["slot_id"] in ctx.faculty_unavailable.get(a["faculty_id"], set()):
            violations.append(f"faculty {a['faculty_id']} unavailable at slot {a['slot_id']}")

        v = ctx.venue_by_id.get(a["venue_id"], {})
        if int(v.get("capacity", 0)) < int(c.get("capacity_required", 0)):
            violations.append(f"course {a['course_id']}: venue capacity exceeded")
        if not set(c.get("required_equipment", []) or []).issubset(
            set(v.get("equipment", []) or [])
        ):
            violations.append(f"course {a['course_id']}: missing equipment")
        need = int(c.get("duration_minutes", 0) or 0)
        slot_len = ctx.slot_dur.get(a["slot_id"], 0)
        if need and slot_len < need:
            violations.append(
                f"course {a['course_id']}: {need} min session does not fit a "
                f"{slot_len} min slot"
            )
        if a["venue_id"] in ctx.venue_allowed and a["slot_id"] not in ctx.venue_allowed[a["venue_id"]]:
            violations.append(f"venue {a['venue_id']} unavailable at slot {a['slot_id']}")

        day = ctx.slot_day.get(a["slot_id"], "?")
        day_mins[(a["faculty_id"], day)] = day_mins.get((a["faculty_id"], day), 0) + ctx.slot_dur.get(
            a["slot_id"], 60
        )

    for (fid, day), mins in day_mins.items():
        limit = int(ctx.faculty_by_id.get(fid, {}).get("max_hours_per_day", 6)) * 60
        if mins > limit:
            violations.append(f"faculty {fid} exceeds daily limit on {day}")

    if max_consecutive and max_consecutive > 0:
        runs: Dict[Tuple[int, str], List[int]] = {}
        for a in assignments:
            day = ctx.slot_day.get(a["slot_id"], "?")
            if a["slot_id"] in ctx.slot_index:
                runs.setdefault((a["faculty_id"], day), []).append(ctx.slot_index[a["slot_id"]])
        for (fid, day), idxs in runs.items():
            idxs = sorted(idxs)
            longest, cur = 1, 1
            for i in range(1, len(idxs)):
                cur = cur + 1 if idxs[i] == idxs[i - 1] + 1 else 1
                longest = max(longest, cur)
            if longest > max_consecutive:
                violations.append(
                    f"faculty {fid} teaches {longest} back-to-back periods on {day} "
                    f"(max {max_consecutive})"
                )

    slot_of = {a["course_id"]: a["slot_id"] for a in assignments}
    for group in session_groups or []:
        seen: Dict[int, int] = {}
        for cid in group:
            sid = slot_of.get(cid)
            if sid is None:
                continue
            if sid in seen:
                violations.append(f"sessions {seen[sid]} and {cid} share slot {sid}")
            seen[sid] = cid

    # Declarative user rules (audited with the same severity as built-ins).
    live = [a for a in assignments if a["course_id"] in course_by_id]
    if ctx.rules:
        violations.extend(ctx.rule_violations(to_map(live)))
    return violations
