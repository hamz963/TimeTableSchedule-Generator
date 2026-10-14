"""Timetable analytics computations."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List


def compute_analytics(
    assignments: List[Dict[str, int]],
    faculty: List[Dict[str, Any]],
    venues: List[Dict[str, Any]],
    slots: List[Dict[str, Any]],
    solver_time_ms: int = 0,
    solver_status: str = "unknown",
) -> Dict[str, Any]:
    faculty_by_id = {f["id"]: f for f in faculty}
    slot_by_id = {s["id"]: s for s in slots}

    # Faculty workload: minutes per faculty per day + distinct days.
    workload: Dict[int, Dict[str, Any]] = {}
    mins_per_faculty_day: Dict[int, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    days_per_faculty: Dict[int, set] = defaultdict(set)
    for a in assignments:
        fid = a["faculty_id"]
        slot = slot_by_id.get(a["slot_id"], {})
        day = str(slot.get("day_of_week", "?"))
        dur = int(slot.get("duration_minutes", 60))
        mins_per_faculty_day[fid][day] += dur
        days_per_faculty[fid].add(day)
    for f in faculty:
        fid = f["id"]
        per_day = dict(mins_per_faculty_day.get(fid, {}))
        workload[fid] = {
            "name": f.get("name", ""),
            "minutes_per_day": per_day,
            "total_minutes": sum(per_day.values()),
            "days_used": len(days_per_faculty.get(fid, set())),
        }

    # Room utilization: booked slots / total available slots per venue.
    venue_avail: Dict[int, int] = {}
    for v in venues:
        avail = v.get("available_slots") or [s["id"] for s in slots]
        venue_avail[v["id"]] = len(avail) or len(slots)
    booked: Dict[int, int] = defaultdict(int)
    for a in assignments:
        booked[a["venue_id"]] += 1
    room_utilization = {}
    for v in venues:
        vid = v["id"]
        total = venue_avail.get(vid, 0) or 1
        room_utilization[vid] = {
            "name": v.get("name", ""),
            "booked": booked.get(vid, 0),
            "available": total,
            "utilization_pct": round(100.0 * booked.get(vid, 0) / total, 2),
        }

    # Preference satisfaction.
    pref_hits = 0
    for a in assignments:
        f = faculty_by_id.get(a["faculty_id"], {})
        if a["slot_id"] in (f.get("preferences", []) or []):
            pref_hits += 1
    total = len(assignments) or 1
    slots_filled_pct = round(100.0 * len(assignments) / max(len(slots), 1), 2)

    return {
        "faculty_workload": workload,
        "room_utilization": room_utilization,
        "preference_satisfaction_pct": round(100.0 * pref_hits / total, 2),
        "slots_filled_pct": slots_filled_pct,
        "solver_time_ms": solver_time_ms,
        "solver_status": solver_status,
    }
