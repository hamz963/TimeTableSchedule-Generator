"""Optimization engine: the single source of truth for timetable solving.

The engine replaces the previous monolithic solver with layered, testable
components:

    context.py     problem normalization + derived indexes (one pass)
    heuristic.py   constructive greedy (feasible-first)
    constraints.py hard-constraint verification
    objectives.py  soft objectives (incremental, shared by SA + metrics)
    optimizer.py   simulated-annealing metaheuristic
    rules.py       declarative user constraint registry (drives the solver)
    metrics.py     quality score + explainability
    pipeline.py    orchestration (CP-SAT exact / greedy + metaheuristic)

`app.services.solver.TimetableSolver` is a thin facade over this package so
existing callers keep working unchanged.
"""
from app.engine.context import ProblemContext, Placement
from app.engine.pipeline import EngineResult, solve
from app.engine.rules import Rule, build_rules, rule_catalog

__all__ = [
    "ProblemContext",
    "Placement",
    "EngineResult",
    "solve",
    "Rule",
    "build_rules",
    "rule_catalog",
]
