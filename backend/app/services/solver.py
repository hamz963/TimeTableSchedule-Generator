"""Solver facade — thin wrapper over :mod:`app.engine`.

Historically this module held the whole CP-SAT model, the greedy heuristic and
the objective code. Those now live in ``app.engine`` (context, exact, heuristic,
optimizer, constraints, objectives, metrics, pipeline) as layered, independently
testable components. This facade preserves the long-standing public surface
``TimetableSolver.generate`` / ``TimetableSolver.verify`` / ``SolverResult`` so
every existing caller and test keeps working unchanged, while gaining the new
capabilities (declarative ``rules``, quality metrics, the SA optimizer).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.engine import pipeline
from app.engine.constraints import verify as _verify
from app.engine.context import build_context
from app.engine.heuristic import greedy_assign as _greedy_assign

__all__ = ["TimetableSolver", "SolverResult"]


@dataclass
class SolverResult:
    status: str  # optimal | feasible | infeasible | timeout
    assignments: List[Dict[str, int]] = field(default_factory=list)
    solver_time_ms: int = 0
    objective_value: Optional[float] = None
    conflicts_resolved: int = 0
    #: Quality score + explainability (populated by the engine).
    metrics: Dict[str, Any] = field(default_factory=dict)
    #: Which engine path ran (exact | heuristic) + optimizer statistics.
    engine: Dict[str, Any] = field(default_factory=dict)


class TimetableSolver:
    """Compatibility facade over the optimization engine."""

    @staticmethod
    def generate(
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
    ) -> SolverResult:
        result = pipeline.solve(
            faculty=faculty, venues=venues, slots=slots, courses=courses,
            time_limit_seconds=time_limit_seconds,
            locked_assignments=locked_assignments, previous=previous,
            session_groups=session_groups, max_consecutive=max_consecutive,
            rules=rules,
        )
        return SolverResult(
            status=result.status,
            assignments=result.assignments,
            solver_time_ms=result.solver_time_ms,
            objective_value=result.objective_value,
            conflicts_resolved=result.conflicts_resolved,
            metrics=result.metrics,
            engine=result.engine,
        )

    @staticmethod
    def verify(
        assignments: List[Dict[str, int]],
        courses: List[Dict[str, Any]],
        faculty: List[Dict[str, Any]],
        venues: List[Dict[str, Any]],
        slots: List[Dict[str, Any]],
        session_groups: Optional[List[List[int]]] = None,
        cancelled: Optional[set] = None,
        max_consecutive: int = 0,
    ) -> List[str]:
        return _verify(
            assignments, courses, faculty, venues, slots,
            session_groups, cancelled, max_consecutive,
        )

    @staticmethod
    def greedy_assign(
        courses: List[Dict[str, Any]],
        faculty: List[Dict[str, Any]],
        venues: List[Dict[str, Any]],
        slots: List[Dict[str, Any]],
        locked_assignments: Optional[List[Dict[str, Any]]] = None,
        previous: Optional[List[Dict[str, int]]] = None,
        session_groups: Optional[List[List[int]]] = None,
        max_consecutive: int = 0,
    ) -> Optional[List[Dict[str, int]]]:
        """Backward-compatible greedy entry point (delegates to the engine)."""
        ctx = build_context(
            faculty, venues, slots, courses,
            session_groups=session_groups,
            locked_assignments=locked_assignments,
            max_consecutive=max_consecutive,
        )
        if previous:
            setattr(ctx, "previous", previous)
        return _greedy_assign(ctx)

    @staticmethod
    def objective_of(
        assignments: List[Dict[str, int]],
        courses: List[Dict[str, Any]],
        faculty: List[Dict[str, Any]],
        venues: List[Dict[str, Any]],
    ) -> float:
        """Soft-objective value of an assignment (preference reward + waste)."""
        course_by_id = {c["id"]: c for c in courses}
        faculty_by_id = {f["id"]: f for f in faculty}
        venue_by_id = {v["id"]: v for v in venues}
        total = 0.0
        for a in assignments:
            c = course_by_id.get(a["course_id"], {})
            f = faculty_by_id.get(a["faculty_id"], {})
            v = venue_by_id.get(a["venue_id"], {})
            if a["slot_id"] in (f.get("preferences", []) or []):
                total -= 10
            total += max(0, int(v.get("capacity", 0)) - int(c.get("capacity_required", 0))) // 10
        return total
