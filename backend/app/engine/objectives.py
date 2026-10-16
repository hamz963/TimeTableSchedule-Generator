"""Soft objectives, expressed once and shared by the optimizer and metrics.

Every term is a *cost to minimize* (rewards are negative costs) so the same
numbers drive the simulated-annealing move evaluation, the reported quality
score, and the CP-SAT soft objective. Sharing one definition is what makes
"the optimizer improved the score by X" a meaningful, honest claim.

Terms
-----
preference   reward a session placed in a slot the teacher marked preferred
time band    reward a session placed in the course's Morning/Afternoon/Evening
room waste   penalize seats wasted (venue capacity beyond what is required)
fairness     penalize a teacher's load bunching onto few days
compactness  penalize idle gaps between a teacher's sessions on a day
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from app.engine.context import ProblemContext, slot_minutes, time_bucket

# Weights chosen so preference/time-band dominate room waste, and fairness /
# compactness act as gentle tie-breakers (matching the CP-SAT model's spirit).
W_PREF = 10.0
W_BAND = 10.0
W_WASTE = 1.0
W_FAIR = 4.0
W_GAP = 2.0

Map = Mapping[int, Tuple[int, int]]  # course_id -> (venue_id, slot_id)


def course_cost(ctx: ProblemContext, cid: int, vid: int, sid: int) -> float:
    """Per-session cost independent of other sessions."""
    course = ctx.course_by_id.get(cid)
    if course is None:
        return 0.0
    faculty = ctx.faculty_by_id.get(course["faculty_id"], {})
    cost = 0.0
    prefs = faculty.get("preferences") or []
    if prefs and sid in prefs:
        cost -= W_PREF
    band = (course.get("preferred_time") or "").strip().capitalize()
    if band in ("Morning", "Afternoon", "Evening"):
        if time_bucket(ctx.slot_start.get(sid, 0)) == band:
            cost -= W_BAND
    venue = ctx.venue_by_id.get(vid, {})
    waste = max(0, int(venue.get("capacity", 0)) - int(course.get("capacity_required", 0)))
    cost += W_WASTE * (waste // 10)
    return cost


def needed_minutes(ctx: ProblemContext) -> Dict[int, int]:
    """Total teaching minutes each faculty must be scheduled (placement-free)."""
    out: Dict[int, int] = {}
    for c in ctx.courses:
        out[c["faculty_id"]] = out.get(c["faculty_id"], 0) + int(c.get("duration_minutes", 60))
    return out


def active_days(ctx: ProblemContext, fid: int) -> int:
    """Days the faculty can actually teach on (slots minus unavailable days)."""
    unavailable = ctx.faculty_unavailable.get(fid, set())
    days = set()
    for sid in ctx.slot_by_id:
        if sid not in unavailable:
            days.add(ctx.slot_day.get(sid, "?"))
    return max(1, len(days))


def faculty_day_penalty(
    ctx: ProblemContext,
    fid: int,
    day: str,
    slot_ids: Iterable[int],
    target_minutes: float,
) -> float:
    """Fairness (bunching) + compactness (idle gaps) for one teacher-day."""
    ids = sorted(sid for sid in slot_ids)
    if not ids:
        return 0.0
    load = sum(ctx.slot_dur.get(sid, 60) for sid in ids)
    # Bunching: load beyond the ideal spread (plus one period of slack).
    typical = ctx.slot_dur.get(ids[0], 60)
    over = max(0.0, load - (target_minutes + typical))
    penalty = W_FAIR * (over / 60.0)
    # Compactness: count idle periods between the first and last session.
    idx = [ctx.slot_index.get(sid) for sid in ids if sid in ctx.slot_index]
    if len(idx) >= 2:
        span = max(idx) - min(idx) + 1
        gaps = span - len(set(idx))
        penalty += W_GAP * gaps
    return penalty


def _faculty_day_slots(ctx: ProblemContext, assignment: Map) -> Dict[Tuple[int, str], List[int]]:
    out: Dict[Tuple[int, str], List[int]] = {}
    for cid, (vid, sid) in assignment.items():
        course = ctx.course_by_id.get(cid)
        if course is None:
            continue
        day = ctx.slot_day.get(sid, "?")
        out.setdefault((course["faculty_id"], day), []).append(sid)
    return out


def total_cost(ctx: ProblemContext, assignment: Map) -> float:
    """Full soft-objective cost of a complete assignment (lower is better)."""
    cost = 0.0
    for cid, (vid, sid) in assignment.items():
        cost += course_cost(ctx, cid, vid, sid)
    need = needed_minutes(ctx)
    for (fid, day), sids in _faculty_day_slots(ctx, assignment).items():
        active = active_days(ctx, fid)
        target = need.get(fid, 0) / active
        cost += faculty_day_penalty(ctx, fid, day, sids, target)
    return cost


def breakdown(ctx: ProblemContext, assignment: Map) -> Dict[str, float]:
    """Decompose total cost into named components for explainability."""
    pref_hit = band_hit = 0
    waste = 0.0
    for cid, (vid, sid) in assignment.items():
        course = ctx.course_by_id.get(cid)
        if course is None:
            continue
        faculty = ctx.faculty_by_id.get(course["faculty_id"], {})
        if sid in (faculty.get("preferences") or []):
            pref_hit += 1
        band = (course.get("preferred_time") or "").strip().capitalize()
        if band in ("Morning", "Afternoon", "Evening") and time_bucket(ctx.slot_start.get(sid, 0)) == band:
            band_hit += 1
        venue = ctx.venue_by_id.get(vid, {})
        waste += max(0, int(venue.get("capacity", 0)) - int(course.get("capacity_required", 0))) // 10

    need = needed_minutes(ctx)
    fair = gaps = 0.0
    for (fid, day), sids in _faculty_day_slots(ctx, assignment).items():
        active = active_days(ctx, fid)
        target = need.get(fid, 0) / active
        ids = sorted(sids)
        load = sum(ctx.slot_dur.get(sid, 60) for sid in ids)
        typical = ctx.slot_dur.get(ids[0], 60)
        fair += W_FAIR * (max(0.0, load - (target + typical)) / 60.0)
        idx = [ctx.slot_index[sid] for sid in ids if sid in ctx.slot_index]
        if len(idx) >= 2:
            gaps += W_GAP * ((max(idx) - min(idx) + 1) - len(set(idx)))
    return {
        "preference_reward": -W_PREF * pref_hit,
        "time_band_reward": -W_BAND * band_hit,
        "room_waste": W_WASTE * waste,
        "fairness": round(fair, 3),
        "compactness": round(gaps, 3),
        "total": round(total_cost(ctx, assignment), 3),
    }


def as_assignment_list(ctx: ProblemContext, assignment: Map) -> List[Dict[str, int]]:
    out: List[Dict[str, int]] = []
    for cid, (vid, sid) in assignment.items():
        course = ctx.course_by_id.get(cid, {})
        out.append({
            "course_id": cid,
            "faculty_id": course.get("faculty_id"),
            "venue_id": vid,
            "slot_id": sid,
        })
    return out
