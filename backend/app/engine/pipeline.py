"""Solve orchestration — the engine's public entry point.

Strategy
--------
* Small, rule-light instances  -> exact CP-SAT (warm-started by a greedy hint,
  guaranteed by a verified greedy fallback). Unchanged optimal behaviour.
* Large instances, or instances carrying hard rules CP-SAT cannot encode
  exactly -> verified greedy seed followed by simulated-annealing optimization.

The chosen path is reported in ``engine["path"]``, and the optimizer records
``cost_start``/``cost_end`` so the improvement it made is auditable.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.config import get_settings
from app.engine.context import ProblemContext, build_context
from app.engine.constraints import verify
from app.engine.exact import JOINT_MODEL_MAX_VARS, ExactSolver
from app.engine.heuristic import greedy_assign
from app.engine.optimizer import optimize
from app.engine import metrics as metrics_mod


@dataclass
class EngineResult:
    status: str  # optimal | feasible | infeasible | timeout
    assignments: List[Dict[str, int]] = field(default_factory=list)
    solver_time_ms: int = 0
    objective_value: Optional[float] = None
    conflicts_resolved: int = 0
    metrics: Dict[str, Any] = field(default_factory=dict)
    engine: Dict[str, Any] = field(default_factory=dict)


def _prev_map(previous: Optional[List[Dict[str, int]]]) -> Optional[Dict[int, Tuple[int, int]]]:
    if not previous:
        return None
    return {p["course_id"]: (p["venue_id"], p["slot_id"]) for p in previous}


def _finish(
    ctx: ProblemContext, status: str, assignments: List[Dict[str, int]],
    started: float, objective: Optional[float], path: str,
    optimizer_stats: Optional[Dict[str, Any]] = None,
) -> EngineResult:
    placement = {a["course_id"]: (a["venue_id"], a["slot_id"]) for a in assignments}
    rule_results = _rule_report(ctx, placement)
    quality = metrics_mod.explain(ctx, placement, rule_results) if assignments else {}
    return EngineResult(
        status=status,
        assignments=assignments,
        solver_time_ms=int((time.perf_counter() - started) * 1000),
        objective_value=objective,
        metrics=quality,
        engine={"path": path, "optimizer": optimizer_stats or {}},
    )


def _rule_report(ctx: ProblemContext, placement: Dict[int, Tuple[int, int]]) -> List[Dict[str, Any]]:
    report = []
    for rule in ctx.rules:
        violations = rule.full_check(ctx, placement) if getattr(rule, "hard", True) else []
        report.append({
            "name": rule.describe(),
            "kind": rule.kind,
            "hard": bool(getattr(rule, "hard", True)),
            "satisfied": not violations,
            "violations": violations[:3],
        })
    return report


def solve(
    faculty: List[Dict[str, Any]],
    venues: List[Dict[str, Any]],
    slots: List[Dict[str, Any]],
    courses: List[Dict[str, Any]],
    time_limit_seconds: float = 5.0,
    locked_assignments: Optional[List[Dict[str, Any]]] = None,
    previous: Optional[List[Dict[str, int]]] = None,
    session_groups: Optional[List[List[int]]] = None,
    max_consecutive: int = 0,
    rules: Optional[List[Any]] = None,
) -> EngineResult:
    started = time.perf_counter()
    ctx = build_context(
        faculty, venues, slots, courses,
        session_groups=session_groups,
        locked_assignments=locked_assignments,
        max_consecutive=max_consecutive,
        rules=rules,
    )
    est_vars = len(courses) * len(venues) * len(slots)
    exact_notes: Optional[Dict[str, Any]] = None

    # ---- Tier 1: exact CP-SAT (small + no uncompilable hard rules) ----------
    if est_vars <= JOINT_MODEL_MAX_VARS and not ctx.rules_need_search():
        solver = ExactSolver(time_limit_seconds=time_limit_seconds)
        solver.add_variables(ctx)
        solver.add_constraints(ctx)
        solver.add_objectives(ctx, previous)
        greedy = greedy_assign(ctx)
        if greedy is not None:
            solver.apply_hint(greedy)
        elapsed = time.perf_counter() - started
        if greedy is not None and elapsed >= time_limit_seconds - 0.8:
            if not verify(greedy, courses, faculty, venues, slots,
                          session_groups, max_consecutive=max_consecutive, ctx=ctx):
                return _finish(ctx, "feasible", greedy, started, None, "greedy-fallback")
        remaining = max(0.2, time_limit_seconds - elapsed - 0.8)
        solve_budget = min(remaining, 1.5) if greedy is not None else remaining
        status, assignments, objective, _ms = solver.solve(solve_budget)
        # Audit the exact result before trusting it: a rule that failed to
        # compile (or any modelling slip) must not be reported as "optimal".
        exact_problems: List[str] = []
        if assignments:
            exact_problems = verify(
                assignments, courses, faculty, venues, slots,
                session_groups, max_consecutive=max_consecutive, ctx=ctx,
            )
        compile_failed = bool(solver.compile_failures)
        if status == "infeasible" and not compile_failed:
            # CP-SAT proved there is no solution: report that, don't downgrade it
            # to "the heuristic got stuck" further down.
            return _finish(ctx, "infeasible", [], started, None, "exact")
        if status in ("optimal", "feasible") and not exact_problems and not compile_failed:
            return _finish(ctx, status, assignments, started, objective, "exact")
        if greedy is not None:
            if not verify(greedy, courses, faculty, venues, slots,
                          session_groups, max_consecutive=max_consecutive, ctx=ctx):
                return _finish(ctx, "feasible", greedy, started, None, "greedy-fallback")
        # Fall through to the verified heuristic tier.
        exact_notes = {
            "status": status,
            "rule_compile_failures": list(solver.compile_failures),
            "violations": exact_problems[:3],
        }

    # ---- Tier 2: greedy seed + simulated annealing --------------------------
    # Restarts matter: the constructor is order-sensitive, so one ordering can
    # get stuck on a satisfiable instance while another succeeds. Previously a
    # single failed pass was reported to the user as "infeasible".
    seed = None
    seed_path = "greedy"
    for variant in range(6):
        seed = greedy_assign(ctx, enforce_rules=True, variant=variant)
        if seed is not None:
            if variant:
                seed_path = f"greedy-restart{variant}"
            break
    if seed is None:
        seed = greedy_assign(ctx, enforce_rules=False)
        seed_path = "greedy-relaxed"
    if seed is None:
        return _finish(ctx, "timeout", [], started, None, "heuristic")

    settings = get_settings()
    cap = float(getattr(settings, "solver_optimize_seconds", 1.5))
    elapsed = time.perf_counter() - started
    budget = min(max(0.2, time_limit_seconds - elapsed - 0.3), max(0.2, cap))
    opt = optimize(ctx, seed, time_budget_s=budget, prev_map=_prev_map(previous))

    assignment = opt.assignments if opt.hard_violations == 0 else seed
    if verify(assignment, courses, faculty, venues, slots, session_groups,
              max_consecutive=max_consecutive, ctx=ctx):
        # Prefer the seed if it is itself clean, otherwise report honestly.
        if not verify(seed, courses, faculty, venues, slots, session_groups,
                      max_consecutive=max_consecutive, ctx=ctx):
            assignment = seed
        else:
            return _finish(ctx, "infeasible", [], started, None, "heuristic")

    stats = {
        "exact_fallback": exact_notes,
        "cost_start": opt.cost_start,
        "cost_end": opt.cost_end,
        "improved": opt.improved,
        "best_score": opt.best_score,
        "converged": opt.converged,
        "improvement_pct": round(
            (opt.cost_start - opt.cost_end) / abs(opt.cost_start) * 100, 2
        ) if opt.cost_start else 0.0,
        "iterations": opt.iterations,
        "accepted": opt.accepted,
        "budget_s": round(budget, 3),
        "seed": seed_path,
    }
    return _finish(ctx, "feasible", assignment, started, opt.cost_end, "heuristic", stats)
