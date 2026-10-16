"""Quality + explainability router.

    GET  /quality/{run_id}       score, sub-scores and per-teacher reasoning
    POST /quality/benchmark      greedy-only vs. optimized on a real/synthetic set
    GET  /quality/benchmark/synthetic   quick synthetic benchmark for dashboards
"""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_scheduler
from app.database import get_db
from app.engine import objectives as obj
from app.engine.constraints import verify
from app.engine.context import build_context
from app.engine.heuristic import greedy_assign
from app.engine.optimizer import optimize
from app.engine import metrics as metrics_mod
from app.schemas.quality import BenchmarkRequest
from app.services.views import get_run_context

router = APIRouter(prefix="/quality", tags=["quality"])


def _synthetic(n_faculty: int, n_rooms: int, n_courses: int, n_slots: int):
    """Build a synthetic instance with real optimization headroom.

    Slots span morning/afternoon/evening (so time-band preferences are
    achievable), rooms have varied capacity (so seat-waste is optimizable),
    and teachers carry distinct preferred slots — so greedy vs. optimized is a
    meaningful comparison rather than a degenerate all-equal case.
    """
    days = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    hours = [8, 10, 13, 15, 17]  # Morning, Morning, Afternoon, Afternoon, Evening
    slots = [
        {"id": i + 1, "day_of_week": days[(i // len(hours)) % 5],
         "start_time": f"{hours[i % len(hours)]:02d}:00",
         "end_time": f"{hours[i % len(hours)] + 1:02d}:00", "duration_minutes": 60}
        for i in range(n_slots)
    ]
    faculty = []
    for i in range(n_faculty):
        # Distinct preferred slot window per teacher so preferences conflict and
        # the optimizer has to resolve them.
        start = (i * 3) % max(1, n_slots)
        prefs = [slots[(start + k) % n_slots]["id"] for k in range(min(4, n_slots))]
        faculty.append({
            "id": i + 1, "name": f"F{i + 1}", "max_hours_per_day": 6, "max_days_per_week": 5,
            "preferences": prefs, "unavailable_slots": [],
        })
    venues = [
        {"id": i + 1, "name": f"R{i + 1}", "capacity": 40 + (i % 5) * 30,
         "equipment": [], "available_slots": []}
        for i in range(n_rooms)
    ]
    bands = ["Morning", "Afternoon", "Evening", ""]
    courses = [
        {"id": i + 1, "name": f"C{i + 1}", "code": f"C{i + 1:04d}",
         "faculty_id": (i % n_faculty) + 1, "capacity_required": 20 + (i % 4) * 15,
         "duration_minutes": 60, "required_equipment": [],
         "preferred_time": bands[i % 4]}
        for i in range(n_courses)
    ]
    return faculty, venues, slots, courses


@router.get("/{run_id}")
def run_quality(run_id: int, db: Session = Depends(get_db),
                _user=Depends(get_current_user)) -> Dict[str, Any]:
    """Score + explain a stored timetable (explainability endpoint)."""
    try:
        ctx_data = get_run_context(db, run_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Schedule run not found")
    summary = ctx_data["summary"] or {}
    masters = summary.get("masters") or {}
    if not masters:
        raise HTTPException(
            status_code=409,
            detail="This run predates quality metrics (no master snapshot stored).",
        )
    ctx = build_context(
        masters["faculty"], masters["venues"], masters["slots"], masters["courses"],
        session_groups=summary.get("session_groups") or [],
    )
    placement = {e.course_id: (e.venue_id, e.slot_id) for e in ctx_data["entries"]}
    report = metrics_mod.explain(ctx, placement)
    return {
        "schedule_run_id": run_id,
        "quality": report,
        "engine": summary.get("engine") or {},
        "solver_status": ctx_data["run"].solver_status,
    }


def _benchmark(faculty, venues, slots, courses, rules, optimize_seconds, seed) -> Dict[str, Any]:
    ctx = build_context(faculty, venues, slots, courses, rules=rules)
    t_seed = greedy_assign(ctx)
    if t_seed is None:
        return {"feasible": False, "detail": "greedy could not find a feasible seed"}
    seed_placement = {a["course_id"]: (a["venue_id"], a["slot_id"]) for a in t_seed}
    greedy_cost = obj.total_cost(ctx, seed_placement)
    result = optimize(ctx, t_seed, time_budget_s=optimize_seconds, seed=seed)
    opt_placement = {a["course_id"]: (a["venue_id"], a["slot_id"]) for a in result.assignments}
    opt_cost = obj.total_cost(ctx, opt_placement)
    violations = verify(result.assignments, courses, faculty, venues, slots, ctx=ctx)
    return {
        "feasible": True,
        "greedy_cost": round(greedy_cost, 3),
        "optimized_cost": round(opt_cost, 3),
        "improvement_pct": round((greedy_cost - opt_cost) / abs(greedy_cost) * 100, 2) if greedy_cost else 0.0,
        "iterations": result.iterations,
        "accepted": result.accepted,
        "optimize_seconds": optimize_seconds,
        "hard_violations_after_optimize": violations,
        "greedy_quality": metrics_mod.score(ctx, seed_placement)["score"],
        "optimized_quality": metrics_mod.score(ctx, opt_placement)["score"],
    }


@router.post("/benchmark", dependencies=[Depends(require_scheduler)])
def benchmark(payload: BenchmarkRequest) -> Dict[str, Any]:
    """Prove the optimizer's value: greedy baseline vs. optimized, same instance."""
    if payload.courses and payload.faculty and payload.venues and payload.slots:
        faculty, venues, slots, courses = (
            payload.faculty, payload.venues, payload.slots, payload.courses)
    else:
        faculty, venues, slots, courses = _synthetic(
            payload.n_faculty, payload.n_rooms, payload.n_courses, payload.n_slots)
    from app.engine.rules import build_rules

    rules = build_rules([r.model_dump() for r in payload.rules])
    return _benchmark(faculty, venues, slots, courses, rules or None,
                      payload.optimize_seconds, payload.seed)


@router.get("/benchmark/synthetic", dependencies=[Depends(require_scheduler)])
def benchmark_synthetic(
    n_faculty: int = Query(50, ge=1, le=1000),
    n_rooms: int = Query(20, ge=1, le=500),
    n_courses: int = Query(100, ge=1, le=5000),
    n_slots: int = Query(40, ge=1, le=2000),
    optimize_seconds: float = Query(1.0, ge=0.05, le=30),
    seed: int = Query(12345),
) -> Dict[str, Any]:
    faculty, venues, slots, courses = _synthetic(n_faculty, n_rooms, n_courses, n_slots)
    return _benchmark(faculty, venues, slots, courses, None, optimize_seconds, seed)
