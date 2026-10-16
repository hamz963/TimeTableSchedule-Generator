"""Constructive greedy heuristic (feasible-first, most-constrained-first).

Pure-Python and model-free: prunes candidates exactly like the CP-SAT model
(capacity, equipment, venue availability) plus faculty unavailability and any
declarative rules, then places courses respecting occupancy, daily workload and
the break rule. Candidate order prefers the previous assignment (delta
stability), then day-spreading, then preferences and least wasted seats.

Returns a feasible assignment when one is reachable greedily, else None.
Used as a CP-SAT solution hint, as a fallback when exact search exceeds its
budget, and as the starting point for the metaheuristic optimizer.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.engine.context import ProblemContext, Placement


def greedy_assign(
    ctx: ProblemContext, enforce_rules: bool = True
) -> Optional[List[Dict[str, int]]]:
    """Construct a feasible assignment (or None when greedy gets stuck).

    enforce_rules=False relaxes only the *relational* hard rules
    (course_before / same_day / no_same_day); local rules and every built-in
    hard constraint still apply. The optimizer uses this to obtain a seed it
    then repairs back onto the hard-feasible manifold.
    """
    courses = ctx.courses
    previous = None  # kept for parity; delta stability flows through ctx.previous
    prev_map: Dict[int, Tuple[int, int]] = {}
    if getattr(ctx, "previous", None):
        for p in ctx.previous:  # type: ignore[attr-defined]
            prev_map[p["course_id"]] = (p["venue_id"], p["slot_id"])

    fac_slot_used: set = set()
    ven_slot_used: set = set()
    fac_day_mins: Dict[Tuple[int, str], int] = {}
    chosen: List[Tuple[int, int, int]] = []
    fac_day_idx: Dict[Tuple[int, str], set] = {}

    group_days: Dict[int, set] = {gi: set() for gi in ctx.group_members}

    def occupy(cid: int, vid: int, sid: int) -> bool:
        c = ctx.course_by_id.get(cid)
        if c is None:
            return False
        if not ctx.placement_allowed(cid, vid, sid):
            return False
        day = ctx.slot_day.get(sid, "?")
        dur = ctx.slot_dur.get(sid, 60)
        fid = c["faculty_id"]
        f = ctx.faculty_by_id.get(fid, {})
        limit = int(f.get("max_hours_per_day", 6)) * 60
        if (fid, sid) in fac_slot_used:
            return False
        if (vid, sid) in ven_slot_used:
            return False
        if fac_day_mins.get((fid, day), 0) + dur > limit:
            return False
        if ctx.max_consecutive and ctx.max_consecutive > 0:
            used = fac_day_idx.get((fid, day), set())
            idx = ctx.slot_index.get(sid)
            if idx is not None:
                run = 1
                j = idx - 1
                while j in used:
                    run += 1
                    j -= 1
                j = idx + 1
                while j in used:
                    run += 1
                    j += 1
                if run > ctx.max_consecutive:
                    return False
        fac_slot_used.add((fid, sid))
        ven_slot_used.add((vid, sid))
        fac_day_mins[(fid, day)] = fac_day_mins.get((fid, day), 0) + dur
        if ctx.max_consecutive and ctx.slot_index.get(sid) is not None:
            fac_day_idx.setdefault((fid, day), set()).add(ctx.slot_index[sid])
        if cid in ctx.group_of:
            group_days[ctx.group_of[cid]].add(day)
        chosen.append((cid, vid, sid))
        return True

    def venue_compatible(c: Dict[str, Any], v: Dict[str, Any]) -> bool:
        if int(v.get("capacity", 0)) < int(c.get("capacity_required", 0)):
            return False
        req = set(c.get("required_equipment", []) or [])
        return req.issubset(set(v.get("equipment", []) or []))

    # Pre-place locked assignments (delta-reschedule pins / fixed slots).
    locked_ids: set = set()
    for lock in ctx.locked_assignments or []:
        c = ctx.course_by_id.get(lock["course_id"])
        v = ctx.venue_by_id.get(lock["venue_id"])
        sid = lock["slot_id"]
        if c is None or v is None or sid not in ctx.slot_by_id:
            return None
        if not venue_compatible(c, v):
            return None
        if v["id"] in ctx.venue_allowed and sid not in ctx.venue_allowed[v["id"]]:
            return None
        if sid in ctx.faculty_unavailable.get(c["faculty_id"], set()):
            return None
        if not occupy(c["id"], v["id"], sid):
            return None
        locked_ids.add(c["id"])

    def candidates(c: Dict[str, Any]) -> List[Tuple[int, int, int]]:
        fid = c["faculty_id"]
        unavail = ctx.faculty_unavailable.get(fid, set())
        prefs = set(ctx.faculty_by_id.get(fid, {}).get("preferences") or [])
        prev = prev_map.get(c["id"])
        cands = []
        for v in ctx.venues:
            if not venue_compatible(c, v):
                continue
            allowed = ctx.venue_allowed.get(v["id"])
            for s in ctx.slots:
                sid = s["id"]
                if sid in unavail:
                    continue
                if allowed is not None and sid not in allowed:
                    continue
                if not ctx.placement_allowed(c["id"], v["id"], sid):
                    continue
                cands.append((c["id"], v["id"], sid))

        def sort_key(k: Tuple[int, int, int]) -> Tuple[int, int, int, int, int, int, int]:
            venue = ctx.venue_by_id.get(k[1], {})
            waste = max(0, int(venue.get("capacity", 0)) - int(c.get("capacity_required", 0)))
            day = ctx.slot_day.get(k[2], "?")
            used_days = group_days.get(ctx.group_of.get(c["id"], -1), set())
            band = (c.get("preferred_time") or "").strip().capitalize()
            band_miss = 0
            if band in ("Morning", "Afternoon", "Evening"):
                from app.engine.context import time_bucket

                band_miss = 0 if time_bucket(ctx.slot_start.get(k[2], 0)) == band else 1
            return (
                0 if prev == (k[1], k[2]) else 1,
                0 if day not in used_days else 1,
                band_miss,
                0 if k[2] in prefs else 1,
                waste,
                k[1],
                k[2],
            )

        return sorted(cands, key=sort_key)

    rest = [c for c in courses if c["id"] not in locked_ids]
    with_counts = [(c, candidates(c)) for c in rest]
    with_counts.sort(key=lambda t: (len(t[1]), t[0]["id"]))

    # Track placements so relational rules (course_before, same_day, ...) can gate.
    placement: Dict[int, Tuple[int, int]] = {
        cid: (vid, sid) for (cid, vid, sid) in chosen
    }

    for c, cands in with_counts:
        placed = False
        for (_cid, vid, sid) in cands:
            if enforce_rules and not ctx.move_allowed(c["id"], vid, sid, placement):
                continue
            if occupy(c["id"], vid, sid):
                placement[c["id"]] = (vid, sid)
                placed = True
                break
        if not placed:
            return None
    return [
        {
            "course_id": cid,
            "faculty_id": ctx.course_by_id[cid]["faculty_id"],
            "venue_id": vid,
            "slot_id": sid,
        }
        for (cid, vid, sid) in chosen
    ]
