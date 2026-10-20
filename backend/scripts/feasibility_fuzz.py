"""Independent feasibility fuzz: the solver's "infeasible" vs. a real DFS oracle.

Why this exists
---------------
The pipeline's ``infeasible`` result comes from a constructive heuristic that has
no backtracking, so "infeasible" cannot be read as a proof. This script builds
random small instances with relational rules, decides feasibility with an
exhaustive DFS (a genuinely independent oracle that shares no code with the
engine), and compares.

The first version of this script was wrong: when the DFS hit its node cap it
returned ``False`` (because ``None`` is falsy in the caller), which silently
turned "gave up" into "infeasible". That is exactly the sin the script is meant
to detect, so the oracle now raises :class:`OracleBudget` and reports UNKNOWN.

Usage
-----
    python scripts/feasibility_fuzz.py [--trials 120] [--seed 7]

Exit code 0 when every comparable instance agrees; 1 on a discrepancy.
"""
from __future__ import annotations

import argparse
import pathlib
import random
import sys
import time
from typing import Any, Dict, List, Set, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.engine.constraints import verify
from app.engine.context import build_context
from app.engine.pipeline import solve
from app.engine.rules import build_rules

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]


class OracleBudget(Exception):
    """The DFS exhausted its node/time budget: feasibility is UNKNOWN."""


def make_instance(rng: random.Random, n_teachers: int, n_courses: int,
                  slots_per_day: int = 3, n_rooms: int = 3):
    slots = [
        {"id": i * 10 + j + 1, "day_of_week": day,
         "start_time": f"{8 + 2 * j:02d}:00", "end_time": f"{9 + 2 * j:02d}:00",
         "duration_minutes": 60}
        for i, day in enumerate(DAYS) for j in range(slots_per_day)
    ]
    faculty = [
        {"id": i + 1, "name": f"T{i + 1}", "max_hours_per_day": 6,
         "max_days_per_week": 5, "preferences": [], "unavailable_slots": []}
        for i in range(n_teachers)
    ]
    venues = [
        {"id": i + 1, "name": f"R{i + 1}", "capacity": 40, "equipment": [],
         "available_slots": []}
        for i in range(n_rooms)
    ]
    courses = [
        {"id": i + 1, "name": f"C{i + 1}", "code": f"C{i + 1}",
         "faculty_id": rng.randint(1, n_teachers), "capacity_required": 30,
         "duration_minutes": 60, "required_equipment": [], "preferred_time": ""}
        for i in range(n_courses)
    ]
    return faculty, venues, slots, courses


def make_rules(rng: random.Random, n_teachers: int, course_ids: List[int]):
    raw: List[Dict[str, Any]] = []
    pairs = list(zip(course_ids, course_ids[1:]))
    if len(course_ids) >= 2 and rng.random() < 0.8:
        a, b = rng.sample(course_ids, 2)
        raw.append({"kind": "course_before",
                    "params": {"course_a": a, "course_b": b}})
    if len(course_ids) >= 3 and rng.random() < 0.5:
        a, b = rng.sample(course_ids, 2)
        raw.append({"kind": "no_same_day",
                    "params": {"course_a": a, "course_b": b}})
    if len(course_ids) >= 3 and rng.random() < 0.35:
        group = rng.sample(course_ids, k=min(2, len(course_ids)))
        raw.append({"kind": "same_day", "params": {"courses": group}})
    for _ in range(rng.randint(0, 2)):
        raw.append({"kind": "forbid_slot",
                    "params": {"entity": "faculty", "id": rng.randint(1, n_teachers),
                               "days": [rng.choice(DAYS)]}})
    del pairs
    return raw


def dfs_feasible(faculty, venues, slots, courses, raw_rules,
                 node_budget: int = 400_000, time_budget: float = 30.0):
    """Exhaustive feasibility check over (slot, room) assignments.

    Returns True/False, or raises OracleBudget. Shares no engine code: rule
    semantics are re-implemented here on purpose, so agreement is meaningful.
    """
    rules = build_rules(raw_rules)
    day_index = {d: i for i, d in enumerate(DAYS)}
    pos = {s["id"]: (day_index[s["day_of_week"]], s["start_time"]) for s in slots}
    day_of = {s["id"]: s["day_of_week"] for s in slots}

    forbidden: Dict[int, Set[int]] = {}
    before: List[Tuple[int, int]] = []
    same_day: List[Set[int]] = []
    no_same_day: List[Tuple[int, int]] = []
    for rule in rules:
        if rule.kind == "forbid_slot":
            if rule.entity in ("faculty", "teacher"):
                for fid in rule.entity_ids:
                    banned = forbidden.setdefault(fid, set())
                    banned |= set(rule.slot_ids)
                    banned |= {s["id"] for s in slots if s["day_of_week"] in rule.days}
            elif rule.entity == "course":
                for cid in rule.entity_ids:
                    banned = forbidden.setdefault(f"course:{cid}", set())
                    banned |= set(rule.slot_ids)
            elif rule.entity in ("venue", "room"):
                for vid in rule.entity_ids:
                    banned = forbidden.setdefault(f"venue:{vid}", set())
                    banned |= set(rule.slot_ids)
        elif rule.kind == "course_before":
            before.extend((a, b) for a in rule.a for b in rule.b)
        elif rule.kind == "same_day":
            same_day.append(set(rule.courses))
        elif rule.kind == "no_same_day":
            no_same_day.extend((a, b) for a in rule.a for b in rule.b)

    by_id = {c["id"]: c for c in courses}
    min_hours = {f["id"]: 0 for f in faculty}
    limit = {f["id"]: int(f["max_hours_per_day"]) * 60 for f in faculty}

    assign: Dict[int, Tuple[int, int]] = {}
    solution: Dict[int, Tuple[int, int]] = {}
    fac_slot: Set[Tuple[int, int]] = set()
    ven_slot: Set[Tuple[int, int]] = set()
    fac_day_min: Dict[Tuple[int, str], int] = {}
    nodes = 0
    started = time.perf_counter()

    def consistent(cid: int, sid: int, vid: int) -> bool:
        course = by_id[cid]
        fid = course["faculty_id"]
        if sid in forbidden.get(fid, set()) or sid in forbidden.get(f"course:{cid}", set()):
            return False
        if vid in forbidden.get(f"venue:{vid}", set()):
            return False
        if (fid, sid) in fac_slot or (vid, sid) in ven_slot:
            return False
        day = day_of[sid]
        if fac_day_min.get((fid, day), 0) + 60 > limit[fid]:
            return False
        p = pos[sid]
        for a, b in before:
            if cid == a and b in assign and not (p < pos[assign[b][1]]):
                return False
            if cid == b and a in assign and not (pos[assign[a][1]] < p):
                return False
        for group in same_day:
            if cid not in group:
                continue
            for other in group:
                if other in assign and day_of[assign[other][1]] != day:
                    return False
        for a, b in no_same_day:
            if cid == a and b in assign and day_of[assign[b][1]] == day:
                return False
            if cid == b and a in assign and day_of[assign[a][1]] == day:
                return False
        return True

    def search(i: int) -> bool:
        nonlocal nodes
        nodes += 1
        if nodes > node_budget or time.perf_counter() - started > time_budget:
            raise OracleBudget
        if i == len(courses):
            solution.update(assign)  # snapshot before the unwinding finallys clear it
            return True
        course = courses[i]
        cid, fid = course["id"], course["faculty_id"]
        for slot in slots:
            sid = slot["id"]
            if sid in forbidden.get(fid, set()):
                continue
            for venue in venues:
                vid = venue["id"]
                if not consistent(cid, sid, vid):
                    continue
                assign[cid] = (vid, sid)
                fac_slot.add((fid, sid))
                ven_slot.add((vid, sid))
                fac_day_min[(fid, day_of[sid])] = fac_day_min.get((fid, day_of[sid]), 0) + 60
                try:
                    if search(i + 1):
                        return True
                finally:
                    assign.pop(cid, None)
                    fac_slot.discard((fid, sid))
                    ven_slot.discard((vid, sid))
                    fac_day_min[(fid, day_of[sid])] -= 60
        return False

    if not search(0):
        return None
    return solution


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=120)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--courses", type=int, default=7)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    false_infeasible = invalid = agree = unknown = oracle_infeasible = 0
    witnesses_checked = 0
    examples: List[str] = []

    for trial in range(args.trials):
        n_teachers = rng.randint(3, 6)
        n_courses = rng.randint(3, args.courses)
        faculty, venues, slots, courses = make_instance(rng, n_teachers, n_courses)
        raw = make_rules(rng, n_teachers, [c["id"] for c in courses])

        try:
            witness = dfs_feasible(faculty, venues, slots, courses, raw)
        except OracleBudget:
            unknown += 1
            continue
        feasible = witness is not None
        if not feasible:
            oracle_infeasible += 1

        rules = build_rules(raw)
        result = solve(faculty, venues, slots, courses, time_limit_seconds=2.0,
                       rules=rules or None)
        solved = result.status in ("optimal", "feasible") and len(result.assignments) == len(courses)

        if solved:
            ctx = build_context(faculty, venues, slots, courses, rules=rules)
            problems = verify(result.assignments, courses, faculty, venues, slots, ctx=ctx)
            if problems:
                invalid += 1
                examples.append(f"trial {trial}: pipeline solution violates {problems[:2]}")
            if not feasible:
                examples.append(
                    f"trial {trial}: pipeline solved an instance the oracle calls "
                    f"infeasible (status={result.status}, path={result.engine.get('path')})"
                )
        if feasible and not solved:
            # Convict only on evidence: the oracle's witness must pass the
            # engine's own verifier, otherwise the oracle is the suspect.
            ctx = build_context(faculty, venues, slots, courses, rules=rules)
            witness_assignments = [
                {"course_id": cid, "faculty_id": next(c["faculty_id"] for c in courses if c["id"] == cid),
                 "venue_id": vid, "slot_id": sid}
                for cid, (vid, sid) in witness.items()
            ]
            witness_problems = verify(witness_assignments, courses, faculty, venues,
                                      slots, ctx=ctx)
            if witness_problems:
                examples.append(
                    f"trial {trial}: ORACLE WITNESS REJECTED by the engine: {witness_problems[:2]}"
                )
                continue
            witnesses_checked += 1
            false_infeasible += 1
            examples.append(
                f"trial {trial}: oracle feasible (witness verified), pipeline {result.status} "
                f"({n_courses} courses, path={result.engine.get('path')}, "
                f"rules={[r['kind'] for r in raw]})"
            )
        if feasible == solved:
            agree += 1

    print(f"instances compared: {args.trials - unknown}")
    print(f"  oracle feasible / pipeline solved: {agree}")
    print(f"  oracle feasible, pipeline infeasible (BUG): {false_infeasible}")
    print(f"  oracle infeasible instances: {oracle_infeasible}")
    print(f"  pipeline solutions failing its own verifier (BUG): {invalid}")
    print(f"  oracle budget exhausted (excluded): {unknown}")
    for line in examples[:10]:
        print("  -", line)
    return 1 if (false_infeasible or invalid) else 0


if __name__ == "__main__":
    sys.exit(main())
