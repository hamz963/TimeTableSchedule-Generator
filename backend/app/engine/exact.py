"""Exact CP-SAT model.

    x[c, v, s] in {0,1} = course c taught in venue v at slot s.

Hard constraints: exactly-once, no faculty/venue double-booking, faculty
unavailability, venue availability, capacity, equipment, daily workload,
locked pins, session-group distinctness, break rule — plus any declarative
rule that can be compiled exactly (see ``rules.py``).

Soft objectives (weighted, minimised): preference + time-band reward, room
waste penalty, delta stability, day-load fairness (minimax).

This module preserves the original model semantics; only its packaging moved
into the engine so the pipeline can choose between exact and heuristic search.
"""
from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional, Tuple

from ortools.sat.python import cp_model

from app.engine.context import ProblemContext, slot_minutes, slot_start_minutes, time_bucket

#: Above this estimated variable count (courses x venues x slots) the exact
#: model build alone (~45 us/var) blows the real-time budget, so the pipeline
#: serves the greedy + metaheuristic path instead.
JOINT_MODEL_MAX_VARS = 25_000


class ExactSolver:
    def __init__(self, time_limit_seconds: float = 5.0, num_workers: int = 8):
        self.time_limit_seconds = time_limit_seconds
        self.num_workers = num_workers
        self.model = cp_model.CpModel()
        self._vars: Dict[Tuple[int, int, int], Any] = {}
        self._by_course: Dict[int, List[Tuple[int, int, int]]] = {}
        self._by_ven_slot: Dict[Tuple[int, int], List[Tuple[int, int, int]]] = {}
        self._by_course_slot: Dict[Tuple[int, int], List[Tuple[int, int, int]]] = {}
        self._courses: List[Dict[str, Any]] = []
        self._status: str = "unknown"
        #: Hard rules that could not be encoded. The pipeline refuses to trust a
        #: model with failures here instead of silently dropping the constraint.
        self.compile_failures: List[str] = []

    def add_variables(self, ctx: ProblemContext) -> None:
        self._courses = ctx.courses
        for c in ctx.courses:
            for v in ctx.venues:
                if int(v.get("capacity", 0)) < int(c.get("capacity_required", 0)):
                    continue
                req = set(c.get("required_equipment", []) or [])
                has = set(v.get("equipment", []) or [])
                if not req.issubset(has):
                    continue
                allowed = ctx.venue_allowed.get(v["id"])
                for s in ctx.slots:
                    if allowed is not None and s["id"] not in allowed:
                        continue
                    if not ctx.placement_allowed(c["id"], v["id"], s["id"]):
                        continue
                    key = (c["id"], v["id"], s["id"])
                    self._vars[key] = self.model.NewBoolVar(
                        f"x_c{c['id']}_v{v['id']}_s{s['id']}"
                    )
                    self._by_course.setdefault(c["id"], []).append(key)
                    self._by_ven_slot.setdefault((v["id"], s["id"]), []).append(key)
                    self._by_course_slot.setdefault((c["id"], s["id"]), []).append(key)

    def add_constraints(self, ctx: ProblemContext) -> None:
        courses, faculty, slots = ctx.courses, ctx.faculty, ctx.slots
        slot_ids = [s["id"] for s in slots]

        # 1. Each course exactly once.
        for c in courses:
            keys = self._by_course.get(c["id"], [])
            if not keys:
                impossible = self.model.NewBoolVar(f"impossible_c{c['id']}")
                self.model.Add(impossible == 0)
                self.model.Add(impossible == 1)
            else:
                self.model.Add(sum(self._vars[k] for k in keys) == 1)

        # 2. No faculty double-booking per slot.
        courses_by_faculty: Dict[int, List[Dict[str, Any]]] = {}
        for c in courses:
            courses_by_faculty.setdefault(c["faculty_id"], []).append(c)
        for fid, fcourses in courses_by_faculty.items():
            for sid in slot_ids:
                lits = [
                    self._vars[k]
                    for c in fcourses
                    for k in self._by_course_slot.get((c["id"], sid), [])
                ]
                if len(lits) > 1:
                    self.model.Add(sum(lits) <= 1)

        # 3. No venue double-booking per slot.
        for keys in self._by_ven_slot.values():
            if len(keys) > 1:
                self.model.Add(sum(self._vars[k] for k in keys) <= 1)

        # 4. Faculty unavailability.
        for c in courses:
            for sid in ctx.faculty_unavailable.get(c["faculty_id"], set()):
                for k in self._by_course_slot.get((c["id"], sid), []):
                    self.model.Add(self._vars[k] == 0)

        # 5. Daily workload limits (minutes per faculty per day).
        for f in faculty:
            fid = f["id"]
            limit_min = int(f.get("max_hours_per_day", 6)) * 60
            fcourses = courses_by_faculty.get(fid, [])
            for day, day_slot_ids in ctx.slot_ids_by_day.items():
                terms = []
                for sid in day_slot_ids:
                    dur_s = ctx.slot_dur.get(sid, 60)
                    for c in fcourses:
                        for k in self._by_course_slot.get((c["id"], sid), []):
                            terms.append(self._vars[k] * dur_s)
                if terms:
                    self.model.Add(sum(terms) <= limit_min)

        # 6. Locked assignments (delta rescheduling pins).
        for lock in ctx.locked_assignments or []:
            key = (lock["course_id"], lock["venue_id"], lock["slot_id"])
            if key in self._vars:
                self.model.Add(self._vars[key] == 1)

        # 7. Session groups: sessions of one course never share a slot.
        for group in ctx.session_groups or []:
            for sid in slot_ids:
                lits = [
                    self._vars[k]
                    for cid in group
                    for k in self._by_course_slot.get((cid, sid), [])
                ]
                if len(lits) > 1:
                    self.model.Add(sum(lits) <= 1)

        # 8. Break rule: sliding window over the ordered day grid, *per teacher*.
        # It used to be applied across every course at once, which capped the
        # whole school at N back-to-back periods and made ordinary instances
        # provably infeasible (only masked because the old pipeline ignored
        # CP-SAT's infeasibility and fell back to greedy).
        if ctx.max_consecutive and ctx.max_consecutive > 0:
            window = ctx.max_consecutive + 1
            for f in faculty:
                fcourses = courses_by_faculty.get(f["id"], [])
                for day_slot_ids in ctx.slot_ids_by_day.values():
                    for i in range(len(day_slot_ids) - window + 1):
                        lits = [
                            self._vars[k]
                            for c in fcourses
                            for sid in day_slot_ids[i:i + window]
                            for k in self._by_course_slot.get((c["id"], sid), [])
                        ]
                        if len(lits) > 1:
                            self.model.Add(sum(lits) <= ctx.max_consecutive)

        # 9. Declarative rules that can be compiled exactly. A rule that fails to
        # compile is recorded (never swallowed): the pipeline then refuses the
        # exact result rather than returning a timetable that breaks a hard rule.
        self.compile_failures = []
        for rule in ctx.rules:
            if not getattr(rule, "hard", True):
                continue
            try:
                if not rule.cp_compile(ctx, self.model, self._vars):
                    self.compile_failures.append(rule.describe())
            except Exception as exc:  # pragma: no cover - defensive
                self.compile_failures.append(f"{rule.describe()}: {exc}")

    def add_objectives(self, ctx: ProblemContext, previous: Optional[List[Dict[str, int]]] = None,
                       fairness_weight: int = 1) -> None:
        prefs_by_course = {
            c["id"]: set(ctx.faculty_by_id.get(c["faculty_id"], {}).get("preferences", []) or [])
            for c in ctx.courses
        }
        band_by_course = {
            c["id"]: (c.get("preferred_time") or "").strip().capitalize() for c in ctx.courses
        }
        waste_by_course_venue = {}
        for c in ctx.courses:
            req = int(c.get("capacity_required", 0))
            for v in ctx.venues:
                waste_by_course_venue[(c["id"], v["id"])] = max(
                    0, int(v.get("capacity", 0)) - req
                ) // 10

        objective_terms = []
        for (cid, vid, sid), var in self._vars.items():
            if cid not in ctx.course_by_id:
                continue
            if sid in prefs_by_course.get(cid, ()):
                objective_terms.append(var * -10)
            band = band_by_course.get(cid, "")
            if band and sid in ctx.band_slots.get(band, ()):
                objective_terms.append(var * -10)
            objective_terms.append(var * waste_by_course_venue.get((cid, vid), 0))

        if previous:
            prev_by_course: Dict[int, set] = {}
            for p in previous:
                prev_by_course.setdefault(p["course_id"], set()).add(
                    (p["course_id"], p["venue_id"], p["slot_id"])
                )
            prev_set = {(p["course_id"], p["venue_id"], p["slot_id"]) for p in previous}
            for key, var in self._vars.items():
                if key not in prev_set and prev_by_course.get(key[0]):
                    objective_terms.append(var * 50)

        if fairness_weight:
            courses_by_faculty: Dict[int, List[int]] = {}
            for c in ctx.courses:
                courses_by_faculty.setdefault(c["faculty_id"], []).append(c["id"])
            max_day_load = self.model.NewIntVar(0, 24 * 60 * 7, "max_day_load")
            for fid, cids in courses_by_faculty.items():
                for day_slot_ids in ctx.slot_ids_by_day.values():
                    terms = []
                    for sid in day_slot_ids:
                        dur_s = ctx.slot_dur.get(sid, 60)
                        for cid in cids:
                            for k in self._by_course_slot.get((cid, sid), []):
                                terms.append(self._vars[k] * dur_s)
                    if terms:
                        self.model.Add(max_day_load >= sum(terms))
            objective_terms.append(max_day_load * fairness_weight)

        if objective_terms:
            self.model.Minimize(sum(objective_terms))

    def apply_hint(self, hint: List[Dict[str, int]]) -> None:
        for a in hint:
            key = (a["course_id"], a["venue_id"], a["slot_id"])
            if key in self._vars:
                self.model.AddHint(self._vars[key], 1)

    def solve(self, time_limit_seconds: Optional[float] = None) -> Tuple[str, List[Dict[str, int]], Optional[float], int]:
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = float(
            time_limit_seconds if time_limit_seconds is not None else self.time_limit_seconds
        )
        solver.parameters.num_search_workers = max(1, min(self.num_workers, os.cpu_count() or 1))
        started = time.perf_counter()
        status = solver.Solve(self.model)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        mapping = {
            cp_model.OPTIMAL: "optimal",
            cp_model.FEASIBLE: "feasible",
            cp_model.INFEASIBLE: "infeasible",
            cp_model.UNKNOWN: "timeout",
        }
        label = mapping.get(status, "unknown")
        assignments: List[Dict[str, int]] = []
        objective: Optional[float] = None
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            try:
                objective = solver.ObjectiveValue()
            except Exception:
                objective = None
            by_id = {c["id"]: c for c in self._courses}
            for (cid, vid, sid), var in self._vars.items():
                if solver.Value(var):
                    course = by_id.get(cid, {})
                    assignments.append({
                        "course_id": cid, "faculty_id": course.get("faculty_id"),
                        "venue_id": vid, "slot_id": sid,
                    })
        return label, assignments, objective, elapsed_ms
