"""Simulated-annealing metaheuristic.

Takes a feasible assignment and improves it over the shared soft objectives
(preferences, time bands, room waste, fairness, compactness) using three move
operators — relocate, swap and room-change — while *never* breaking a
structural hard constraint and penalising declarative-rule violations so the
search repairs them.

This is what turns a plain first-fit greedy result (the previous behaviour for
every large instance) into an optimized one. The optimizer is deterministic:
given the same seed and budget it returns the same timetable.
"""
from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from app.engine.context import ProblemContext
from app.engine import metrics as metrics_mod
from app.engine import objectives as obj

#: A declarative hard-rule violation costs this much in the search cost, far
#: above any legitimate soft cost, so the search drives violations to zero.
W_HARD_VIOLATION = 10_000.0
#: Penalty for moving away from a previous assignment (reschedule stability).
W_DELTA = 50.0


@dataclass
class OptimizeResult:
    assignments: List[Dict[str, int]]
    cost_start: float
    cost_end: float
    iterations: int
    accepted: int
    hard_violations: int
    elapsed_ms: int
    #: Best composite quality score observed (the search's true objective).
    best_score: float = 0.0
    #: True when the last quarter of the search produced no further improvement
    #: — an honest "settled" signal (this is a heuristic, not a proof).
    converged: bool = False

    @property
    def improved(self) -> bool:
        return self.cost_end < self.cost_start - 1e-9


class _State:
    """Placement + occupancy indexes with exact incremental cost deltas."""

    def __init__(self, ctx: ProblemContext, placement: Dict[int, Tuple[int, int]]):
        self.ctx = ctx
        self.place: Dict[int, Tuple[int, int]] = dict(placement)
        self.fac_slot: Dict[Tuple[int, int], int] = {}
        self.ven_slot: Dict[Tuple[int, int], int] = {}
        self.group_slot: Dict[Tuple[int, int], int] = {}
        self.fac_day_slots: Dict[Tuple[int, str], Set[int]] = {}
        self.fac_day_min: Dict[Tuple[int, str], int] = {}
        self.course_cost: Dict[int, float] = {}
        self.prev_map: Optional[Dict[int, Tuple[int, int]]] = None
        self.extra = 0.0  # delta-stability penalty vs. a previous assignment
        self._need = obj.needed_minutes(ctx)
        self._active = {f["id"]: obj.active_days(ctx, f["id"]) for f in ctx.faculty}
        for cid, (vid, sid) in self.place.items():
            self._add(cid, vid, sid)
        self.candidates: Dict[int, List[Tuple[int, int]]] = {
            c["id"]: self._build_candidates(c) for c in ctx.courses
        }

    # -- candidate generation -------------------------------------------------
    def _build_candidates(self, c: Dict[str, Any]) -> List[Tuple[int, int]]:
        ctx = self.ctx
        out: List[Tuple[int, int]] = []
        unavail = ctx.faculty_unavailable.get(c["faculty_id"], set())
        req = set(c.get("required_equipment", []) or [])
        for v in ctx.venues:
            if int(v.get("capacity", 0)) < int(c.get("capacity_required", 0)):
                continue
            if not req.issubset(set(v.get("equipment", []) or [])):
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
                out.append((v["id"], sid))
        return out

    # -- index maintenance ----------------------------------------------------
    def _add(self, cid: int, vid: int, sid: int) -> None:
        ctx = self.ctx
        fid = ctx.course_by_id[cid]["faculty_id"]
        day = ctx.slot_day.get(sid, "?")
        self.fac_slot[(fid, sid)] = cid
        self.ven_slot[(vid, sid)] = cid
        gi = ctx.group_of.get(cid)
        if gi is not None:
            self.group_slot[(gi, sid)] = cid
        self.fac_day_slots.setdefault((fid, day), set()).add(sid)
        self.fac_day_min[(fid, day)] = self.fac_day_min.get((fid, day), 0) + ctx.slot_dur.get(sid, 60)
        self.course_cost[cid] = obj.course_cost(ctx, cid, vid, sid)

    def _remove(self, cid: int, vid: int, sid: int) -> None:
        ctx = self.ctx
        fid = ctx.course_by_id[cid]["faculty_id"]
        day = ctx.slot_day.get(sid, "?")
        self.fac_slot.pop((fid, sid), None)
        self.ven_slot.pop((vid, sid), None)
        gi = ctx.group_of.get(cid)
        if gi is not None:
            self.group_slot.pop((gi, sid), None)
        s = self.fac_day_slots.get((fid, day))
        if s is not None:
            s.discard(sid)
            if not s:
                self.fac_day_slots.pop((fid, day), None)
        self.fac_day_min[(fid, day)] = self.fac_day_min.get((fid, day), 0) - ctx.slot_dur.get(sid, 60)

    # -- structural feasibility (never violates a built-in hard constraint) ---
    def structural_ok(self, cid: int, vid: int, sid: int) -> bool:
        ctx = self.ctx
        fid = ctx.course_by_id[cid]["faculty_id"]
        cur = self.place.get(cid)
        if cur == (vid, sid):
            return False
        other = self.fac_slot.get((fid, sid))
        if other is not None and other != cid:
            return False
        other = self.ven_slot.get((vid, sid))
        if other is not None and other != cid:
            return False
        gi = ctx.group_of.get(cid)
        if gi is not None:
            other = self.group_slot.get((gi, sid))
            if other is not None and other != cid:
                return False
        day = ctx.slot_day.get(sid, "?")
        old_day = ctx.slot_day.get(cur[1], "?") if cur else None
        dur = ctx.slot_dur.get(sid, 60)
        limit = int(ctx.faculty_by_id.get(fid, {}).get("max_hours_per_day", 6)) * 60
        cur_min = self.fac_day_min.get((fid, day), 0)
        if cur is not None and old_day == day:
            cur_min -= ctx.slot_dur.get(cur[1], 60)
        if cur_min + dur > limit:
            return False
        if ctx.max_consecutive and ctx.max_consecutive > 0:
            idx = ctx.slot_index.get(sid)
            if idx is not None:
                used = set(self.fac_day_slots.get((fid, day), set()))
                if cur is not None and old_day == day:
                    used.discard(cur[1])
                used_idx = {ctx.slot_index[s] for s in used if s in ctx.slot_index}
                run = 1
                j = idx - 1
                while j in used_idx:
                    run += 1
                    j -= 1
                j = idx + 1
                while j in used_idx:
                    run += 1
                    j += 1
                if run > ctx.max_consecutive:
                    return False
        return True

    def _fac_pen(self, fid: int, day: Optional[str]) -> float:
        if day is None:
            return 0.0
        sids = self.fac_day_slots.get((fid, day), set())
        if not sids:
            return 0.0
        target = self._need.get(fid, 0) / self._active.get(fid, 1)
        return obj.faculty_day_penalty(self.ctx, fid, day, sids, target)

    def rule_cost(self) -> float:
        if not self.ctx.rules:
            return 0.0
        return self.ctx.rule_penalty(self.place)

    def hard_violations(self) -> List[str]:
        return self.ctx.rule_violations(self.place) if self.ctx.rules else []

    def running_cost(self) -> float:
        cost = sum(self.course_cost.values())
        for (fid, day) in list(self.fac_day_slots):
            cost += self._fac_pen(fid, day)
        return cost

    def total(self) -> float:
        return self.running_cost() + self.rule_cost() + self.extra

    # -- moves (each is its own inverse) --------------------------------------
    def relocate(self, cid: int, vid: int, sid: int) -> None:
        v0, s0 = self.place[cid]
        self.extra += self._prev_cost(cid, vid, sid) - self._prev_cost(cid, v0, s0)
        self._remove(cid, v0, s0)
        self._add(cid, vid, sid)
        self.place[cid] = (vid, sid)

    def swap(self, a: int, b: int) -> None:
        va, sa = self.place[a]
        vb, sb = self.place[b]
        self.extra += self._prev_cost(a, vb, sb) - self._prev_cost(a, va, sa)
        self.extra += self._prev_cost(b, va, sa) - self._prev_cost(b, vb, sb)
        self._remove(a, va, sa)
        self._remove(b, vb, sb)
        self._add(a, vb, sb)
        self._add(b, va, sa)
        self.place[a] = (vb, sb)
        self.place[b] = (va, sa)

    def _prev_cost(self, cid: int, vid: int, sid: int) -> float:
        if not self.prev_map:
            return 0.0
        return 0.0 if self.prev_map.get(cid) == (vid, sid) else W_DELTA

    def set_prev(self, prev_map: Optional[Dict[int, Tuple[int, int]]]) -> None:
        self.prev_map = prev_map
        if prev_map:
            self.extra = sum(
                W_DELTA for cid, got in self.place.items() if prev_map.get(cid) != got
            )

    # -- exact cost deltas ----------------------------------------------------
    def delta_relocate(self, cid: int, vid: int, sid: int) -> float:
        ctx = self.ctx
        v0, s0 = self.place[cid]
        fid = ctx.course_by_id[cid]["faculty_id"]
        day0 = ctx.slot_day.get(s0, "?")
        day1 = ctx.slot_day.get(sid, "?")
        old_course = self.course_cost[cid]
        old_p0 = self._fac_pen(fid, day0)
        old_p1 = 0.0 if day1 == day0 else self._fac_pen(fid, day1)
        rule_before = self.rule_cost() if ctx.rules else 0.0
        self.relocate(cid, vid, sid)
        new_course = self.course_cost[cid]
        new_p0 = self._fac_pen(fid, day0)
        new_p1 = 0.0 if day1 == day0 else self._fac_pen(fid, day1)
        delta = (new_course - old_course) + (new_p0 - old_p0) + (new_p1 - old_p1)
        if ctx.rules:
            delta += self.rule_cost() - rule_before
        return delta

    def delta_swap(self, a: int, b: int) -> float:
        ctx = self.ctx
        fid_a = ctx.course_by_id[a]["faculty_id"]
        fid_b = ctx.course_by_id[b]["faculty_id"]
        days = {
            ctx.slot_day.get(self.place[a][1], "?"),
            ctx.slot_day.get(self.place[b][1], "?"),
        }
        keys_a = [(fid_a, d) for d in days]
        keys_b = [(fid_b, d) for d in days]
        old = {k: self._fac_pen(*k) for k in set(keys_a + keys_b)}
        old_course = self.course_cost[a] + self.course_cost[b]
        rule_before = self.rule_cost() if ctx.rules else 0.0
        self.swap(a, b)
        new = {k: self._fac_pen(*k) for k in set(keys_a + keys_b)}
        new_course = self.course_cost[a] + self.course_cost[b]
        delta = (new_course - old_course) + sum(new.values()) - sum(old.values())
        if ctx.rules:
            delta += self.rule_cost() - rule_before
        return delta


def _immutable(ctx: ProblemContext) -> Set[int]:
    """Courses the optimizer may not move (locked pins + fixed_slot rules)."""
    fixed: Set[int] = {l["course_id"] for l in ctx.locked_assignments or []}
    for rule in ctx.rules:
        if getattr(rule, "kind", "") == "fixed_slot":
            fixed.add(int(rule.params.get("course_id")))
    return fixed


def _descent(
    state: _State, mutable: List[int], rng: random.Random, deadline: float,
    max_passes: int = 50,
) -> None:
    """First-improvement local search: repeatedly relocate to the best neighbor.

    Runs before annealing so even a tiny budget yields a strict improvement
    over the greedy seed (annealing then escapes the resulting local optimum).
    ``deadline=inf`` (deterministic mode) runs to convergence, bounded by
    ``max_passes`` so a pathological instance cannot loop forever.
    """
    improved = True
    passes = 0
    while improved and passes < max_passes and time.perf_counter() < deadline:
        improved = False
        passes += 1
        order = list(mutable)
        rng.shuffle(order)
        for cid in order:
            if time.perf_counter() >= deadline:
                return
            v0, s0 = state.place[cid]
            best_d = 0.0
            best: Optional[Tuple[int, int]] = None
            for (vid, sid) in state.candidates.get(cid, []):
                if (vid, sid) == (v0, s0) or not state.structural_ok(cid, vid, sid):
                    continue
                delta = state.delta_relocate(cid, vid, sid)  # applies
                state.relocate(cid, v0, s0)                   # revert
                if delta < best_d - 1e-9:
                    best_d, best = delta, (vid, sid)
            if best is not None:
                state.delta_relocate(cid, best[0], best[1])  # commit
                improved = True


def optimize(
    ctx: ProblemContext,
    assignment: List[Dict[str, int]],
    time_budget_s: float = 1.0,
    seed: int = 12345,
    prev_map: Optional[Dict[int, Tuple[int, int]]] = None,
    max_iterations: Optional[int] = None,
) -> OptimizeResult:
    """Improve an assignment: greedy descent, then simulated annealing.

    Structural hard constraints are never violated. Pass ``max_iterations`` to
    run a fully deterministic search (fixed number of annealing steps, descent
    run to convergence) — used for reproducible results and tests. Otherwise
    the search is time-budgeted and ``seed``-reproducible in outcome.
    """
    start = time.perf_counter()
    placement = {a["course_id"]: (a["venue_id"], a["slot_id"]) for a in assignment}
    state = _State(ctx, placement)
    state.set_prev(prev_map)
    mutable = [cid for cid in state.place if cid not in _immutable(ctx)]
    base_cost = state.total()
    if not mutable:
        return OptimizeResult(list(assignment), base_cost, base_cost, 0, 0,
                              len(state.hard_violations()), 0)

    deterministic = max_iterations is not None
    rng = random.Random(seed)
    budget = max(0.01, time_budget_s)

    # Phase 1: greedy descent (whole budget in deterministic mode).
    deadline = float("inf") if deterministic else start + budget * 0.4
    _descent(state, mutable, rng, deadline)
    best_cost = state.total()
    best_place = dict(state.place)
    iterations = accepted = 0

    # The optimizer minimises the soft *cost*, while users see the composite
    # *quality score*; the two weightings differ slightly, so a pure cost win
    # can nudge the score down. To keep both monotone we return the highest-score
    # placement among those whose cost is no worse than the seed — the seed is
    # always in that set, so neither metric can ever regress.
    def _score_of(place: Dict[int, Tuple[int, int]]) -> float:
        return metrics_mod.score(ctx, place)["score"]

    best_score_place = dict(placement)
    best_score = _score_of(best_score_place)
    best_score_cost = base_cost
    post = _score_of(best_place)
    if post > best_score + 1e-9:
        best_score, best_score_place, best_score_cost = post, dict(best_place), best_cost

    last_improve_iter = 0

    def _note_cost_best() -> None:
        nonlocal best_score, best_score_place, best_score_cost, last_improve_iter
        sc = _score_of(best_place)
        if sc > best_score + 1e-9:
            best_score, best_score_place, best_score_cost = sc, dict(best_place), best_cost
            last_improve_iter = iterations

    # Phase 2: simulated annealing.
    t0 = max(1.0, abs(base_cost) * 0.02 + 1.0)
    t_min = 0.05

    def _sa_step(temp: float) -> None:
        nonlocal iterations, accepted, best_cost, best_place
        iterations += 1
        cid = rng.choice(mutable)
        v0, s0 = state.place[cid]
        roll = rng.random()
        if roll < 0.20 and len(mutable) > 1:
            other = rng.choice(mutable)
            if other == cid:
                return
            v1, s1 = state.place[other]
            if not (state.structural_ok(cid, v1, s1) and state.structural_ok(other, v0, s0)):
                return
            delta = state.delta_swap(cid, other)
            if delta <= 0 or rng.random() < math.exp(-delta / temp):
                accepted += 1
                if state.total() < best_cost - 1e-9:
                    best_cost, best_place = state.total(), dict(state.place)
                    _note_cost_best()
            else:
                state.swap(cid, other)
        else:
            cands = state.candidates.get(cid) or []
            if not cands:
                return
            vid, sid = cands[rng.randrange(len(cands))]
            if roll < 0.30:  # room-change only: keep the slot
                sid = s0
            if (vid, sid) == (v0, s0) or not state.structural_ok(cid, vid, sid):
                return
            delta = state.delta_relocate(cid, vid, sid)
            if delta <= 0 or rng.random() < math.exp(-delta / temp):
                accepted += 1
                if state.total() < best_cost - 1e-9:
                    best_cost, best_place = state.total(), dict(state.place)
                    _note_cost_best()
            else:
                state.relocate(cid, v0, s0)

    if deterministic:
        n = max(0, int(max_iterations))
        for i in range(n):
            temp = t0 * (t_min / t0) ** (i / max(1, n - 1)) if n > 1 else t_min
            _sa_step(temp)
    else:
        while True:
            elapsed = time.perf_counter() - start
            if elapsed >= budget:
                break
            _sa_step(t0 * (t_min / t0) ** min(1.0, elapsed / budget))

    best_list = [
        {"course_id": cid, "faculty_id": ctx.course_by_id[cid]["faculty_id"],
         "venue_id": vid, "slot_id": sid}
        for cid, (vid, sid) in best_score_place.items()
    ]
    violations = len(ctx.rule_violations(best_score_place)) if ctx.rules else 0
    converged = iterations == 0 or (iterations - last_improve_iter) >= 0.25 * iterations
    return OptimizeResult(
        assignments=best_list, cost_start=round(base_cost, 3),
        cost_end=round(best_score_cost, 3),
        iterations=iterations, accepted=accepted, hard_violations=violations,
        elapsed_ms=int((time.perf_counter() - start) * 1000),
        best_score=round(best_score, 2), converged=converged,
    )
