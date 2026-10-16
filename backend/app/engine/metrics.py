"""Quality scoring + explainability.

Turns a finished timetable into (a) a single 0-100 quality score built from
transparent sub-scores and (b) a human-readable explanation: what each score
means, which teachers/days drive it, and which declared rules were honoured.

All numbers come from the shared objective definitions, so the score moves in
lock-step with what the optimizer actually minimises.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from app.engine import objectives as obj
from app.engine.context import ProblemContext, time_bucket

# Sub-score weights (renormalised over the components a problem actually has).
WEIGHTS = {
    "preference_satisfaction": 0.35,
    "time_band_satisfaction": 0.20,
    "room_efficiency": 0.20,
    "fairness": 0.15,
    "compactness": 0.10,
}


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def score(ctx: ProblemContext, placement: Dict[int, Tuple[int, int]]) -> Dict[str, Any]:
    """Composite quality score with a full sub-score breakdown."""
    n = len(placement) or 1
    pref_total = pref_hit = 0
    band_total = band_hit = 0
    req_sum = cap_sum = 0
    for cid, (vid, sid) in placement.items():
        course = ctx.course_by_id.get(cid)
        if course is None:
            continue
        prefs = ctx.faculty_by_id.get(course["faculty_id"], {}).get("preferences") or []
        if prefs:
            pref_total += 1
            pref_hit += 1 if sid in prefs else 0
        band = (course.get("preferred_time") or "").strip().capitalize()
        if band in ("Morning", "Afternoon", "Evening"):
            band_total += 1
            band_hit += 1 if time_bucket(ctx.slot_start.get(sid, 0)) == band else 0
        req_sum += int(course.get("capacity_required", 0))
        cap_sum += max(int(ctx.venue_by_id.get(vid, {}).get("capacity", 0)), 1)

    subs: Dict[str, float] = {}
    if pref_total:
        subs["preference_satisfaction"] = pref_hit / pref_total
    if band_total:
        subs["time_band_satisfaction"] = band_hit / band_total
    if cap_sum:
        subs["room_efficiency"] = _clamp01(req_sum / cap_sum)

    # Fairness: 1 = perfectly even day load per teacher, 0 = all on one day.
    need = obj.needed_minutes(ctx)
    fac_day: Dict[Tuple[int, str], int] = defaultdict(int)
    for cid, (_v, sid) in placement.items():
        fac_day[(ctx.course_by_id[cid]["faculty_id"], ctx.slot_day.get(sid, "?"))] += ctx.slot_dur.get(sid, 60)
    imbalances = []
    for fid in {k[0] for k in fac_day}:
        active = obj.active_days(ctx, fid)
        target = need.get(fid, 0) / active
        loads = [fac_day.get((fid, d), 0) for d in ctx.days]
        worst = max(loads) if loads else 0
        imbalances.append(_clamp01(1.0 - max(0.0, worst - target) / max(target, 1.0)))
    if imbalances:
        subs["fairness"] = sum(imbalances) / len(imbalances)

    # Compactness: 1 - (idle gaps / possible gaps).
    gaps = span_total = 0
    fac_day_slots: Dict[Tuple[int, str], List[int]] = defaultdict(list)
    for cid, (_v, sid) in placement.items():
        fac_day_slots[(ctx.course_by_id[cid]["faculty_id"], ctx.slot_day.get(sid, "?"))].append(
            ctx.slot_index.get(sid, 0)
        )
    for idxs in fac_day_slots.values():
        if len(idxs) >= 2:
            span = max(idxs) - min(idxs) + 1
            span_total += span
            gaps += span - len(set(idxs))
    if span_total:
        subs["compactness"] = _clamp01(1.0 - gaps / span_total)

    denom = sum(WEIGHTS[k] for k in subs) or 1.0
    composite = sum(WEIGHTS[k] * v for k, v in subs.items()) / denom * 100.0
    return {
        "score": round(composite, 1),
        "sub_scores": {k: round(v * 100, 1) for k, v in subs.items()},
        "breakdown": obj.breakdown(ctx, placement),
        "counts": {
            "sessions": len(placement),
            "preference_hits": pref_hit,
            "preference_scored": pref_total,
            "band_hits": band_hit,
            "band_scored": band_total,
        },
        "grade": _grade(composite),
    }


def _grade(composite: float) -> str:
    for threshold, label in ((90, "excellent"), (75, "good"), (60, "fair"), (40, "weak")):
        if composite >= threshold:
            return label
    return "poor"


def explain(
    ctx: ProblemContext,
    placement: Dict[int, Tuple[int, int]],
    rule_results: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Human-readable explanation of why the timetable looks the way it does."""
    sc = score(ctx, placement)

    fac_day: Dict[int, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for cid, (_v, sid) in placement.items():
        fid = ctx.course_by_id[cid]["faculty_id"]
        fac_day[fid][ctx.slot_day.get(sid, "?")] += ctx.slot_dur.get(sid, 60)

    teachers = []
    for f in ctx.faculty:
        per_day = dict(fac_day.get(f["id"], {}))
        days = sorted(per_day)
        total = sum(per_day.values())
        notes = []
        if days and len(days) < len(ctx.days):
            busiest = max(per_day, key=per_day.get)
            if per_day[busiest] > max(60, total / max(len(days), 1) * 1.5):
                notes.append(f"heaviest day {busiest} ({per_day[busiest]} min) — consider spreading")
        teachers.append({
            "id": f["id"],
            "name": f.get("name", f"Teacher {f['id']}"),
            "sessions": sum(1 for cid in placement if ctx.course_by_id[cid]["faculty_id"] == f["id"]),
            "total_minutes": total,
            "days": days,
            "minutes_per_day": per_day,
            "notes": notes,
        })

    reasons: List[str] = []
    b = sc["breakdown"]
    if sc["counts"]["preference_scored"]:
        reasons.append(
            f"{sc['counts']['preference_hits']}/{sc['counts']['preference_scored']} sessions "
            "landed in a teacher-preferred slot."
        )
    if sc["counts"]["band_scored"]:
        reasons.append(
            f"{sc['counts']['band_hits']}/{sc['counts']['band_scored']} sessions honoured the "
            "course's preferred time of day."
        )
    reasons.append(f"Room waste penalty term: {b['room_waste']:.1f} (lower is better).")
    reasons.append(f"Fairness penalty term: {b['fairness']:.1f}; compactness term: {b['compactness']:.1f}.")

    return {
        "score": sc,
        "teachers": teachers,
        "reasons": reasons,
        "rules": rule_results or [],
    }
