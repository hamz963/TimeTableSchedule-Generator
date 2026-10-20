"""Realistic-instance benchmark: mixed session lengths, cohorts, lab equipment.

The synthetic benchmark (``/quality/benchmark``) uses uniform 60-minute sessions,
one teacher per course and no cohort constraints, which flatters the scheduler.
This script builds a university-shaped instance instead:

* slot grid with 60 / 90 / 120-minute blocks (labs and double periods exist),
* sessions whose length must fit the block,
* cohorts (student groups) that cannot attend two classes at once,
* labs that require equipment, lecture halls with different capacities,
* teachers with several courses and some unavailable days.

It reports wall-clock time, status, path, quality and independent violations.

    python scripts/bench_realistic.py --sessions 150 400 800
"""
from __future__ import annotations

import argparse
import json
import pathlib
import random
import sys
import time
from typing import Any, Dict, List

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.engine import metrics as metrics_mod
from app.engine.constraints import verify
from app.engine.context import build_context
from app.engine.pipeline import solve

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]

#: (start, end) blocks — the grid a real timetable is built on.
BLOCKS = [("08:00", "10:00"), ("10:00", "11:30"), ("11:30", "12:30"),
          ("13:00", "14:30"), ("14:30", "15:30"), ("15:30", "17:30")]


def make_instance(seed: int, n_sessions: int):
    rng = random.Random(seed)
    slots: List[Dict[str, Any]] = []
    sid = 1
    for day in DAYS:
        for start, end in BLOCKS:
            sh, sm = map(int, start.split(":"))
            eh, em = map(int, end.split(":"))
            slots.append({
                "id": sid, "day_of_week": day, "start_time": start, "end_time": end,
                "duration_minutes": (eh * 60 + em) - (sh * 60 + sm),
            })
            sid += 1


    # ~40 % teaching load: a teacher who is banned one day must still fit, so the
    # generator caps each teacher at half of their remaining slots.
    n_teachers = max(4, n_sessions // 10)
    faculty: List[Dict[str, Any]] = []
    load_cap: Dict[int, int] = {}
    for i in range(n_teachers):
        unavailable: List[int] = []
        if rng.random() < 0.15:
            banned_day = rng.choice(DAYS)
            unavailable = [s["id"] for s in slots if s["day_of_week"] == banned_day]
        faculty.append({
            "id": i + 1, "name": f"Dr. {i + 1}", "max_hours_per_day": 6,
            "max_days_per_week": 5, "preferences": [],
            "unavailable_slots": unavailable,
        })
        load_cap[i + 1] = max(2, (len(slots) - len(unavailable)) // 2)
    assigned: Dict[int, int] = {f["id"]: 0 for f in faculty}

    def pick_teacher() -> int:
        eligible = [fid for fid in assigned if assigned[fid] < load_cap[fid]]
        if not eligible:
            # Never generate an instance that is infeasible by construction.
            new_id = len(faculty) + 1
            faculty.append({
                "id": new_id, "name": f"Dr. {new_id}", "max_hours_per_day": 6,
                "max_days_per_week": 5, "preferences": [], "unavailable_slots": [],
            })
            assigned[new_id] = 0
            load_cap[new_id] = max(2, len(slots) // 2)
            eligible = [new_id]
        fid = rng.choice(eligible)
        assigned[fid] += 1
        return fid

    # Cohorts: 4-6 courses per group. Names are unique so a cohort cannot
    # accidentally accumulate more sessions than the week has slots.
    courses: List[Dict[str, Any]] = []
    groups: Dict[str, List[int]] = {}
    cid = 1
    cohort_no = 0
    while len(courses) < n_sessions:
        cohort_no += 1
        cohort = f"Y{rng.randint(1, 3)}-G{cohort_no:03d}"
        for _ in range(rng.randint(4, 6)):
            if len(courses) >= n_sessions:
                break
            is_lab = rng.random() < 0.35
            duration = rng.choice([90, 120]) if is_lab else rng.choice([60, 90])
            courses.append({
                "id": cid, "name": f"{cohort}-C{len(courses) + 1}",
                "code": f"C{cid:04d}", "faculty_id": pick_teacher(),
                "capacity_required": 30 if is_lab else rng.choice([30, 45, 150]),
                "duration_minutes": duration,
                "required_equipment": ["lab"] if is_lab else [],
                "student_group": cohort,
                "preferred_time": rng.choice(["", "Morning", "Afternoon", "Evening"]),
            })
            groups.setdefault(cohort, []).append(cid)
            cid += 1

    session_groups = [g for g in groups.values() if len(g) > 1]

    # Rooms are sized from demand so the instance is hard but not impossible by
    # construction: a lab block needs a lab room, a 150-seat lecture needs a hall.
    long_slots = [s for s in slots if s["duration_minutes"] >= 90]
    lab_sessions = [c for c in courses if "lab" in (c["required_equipment"] or [])]
    hall_sessions = [c for c in courses if c["capacity_required"] >= 150]
    small_sessions = [c for c in courses if c["capacity_required"] < 150 and not c["required_equipment"]]
    venues: List[Dict[str, Any]] = []
    next_id = 1

    def add_rooms(count: int, prefix: str, capacity: int, equipment: List[str]) -> None:
        nonlocal next_id
        for i in range(count):
            venues.append({"id": next_id, "name": f"{prefix} {i + 1}",
                           "capacity": capacity, "equipment": equipment,
                           "available_slots": []})
            next_id += 1

    add_rooms(max(1, round(len(lab_sessions) / max(1, len(long_slots)) * 1.3)),
              "Lab", 30, ["lab"])
    add_rooms(max(1, round(len(hall_sessions) / max(1, len(slots)) * 1.3)),
              "Hall", 150, [])
    add_rooms(max(1, round(len(small_sessions) / max(1, len(slots)) * 1.3)),
              "Seminar", 45, [])

    return faculty, venues, slots, courses, session_groups


def run(seed: int, n_sessions: int) -> Dict[str, Any]:
    faculty, venues, slots, courses, groups = make_instance(seed, n_sessions)
    ctx = build_context(faculty, venues, slots, courses, session_groups=groups)
    started = time.perf_counter()
    result = solve(faculty, venues, slots, courses, time_limit_seconds=5.0,
                   session_groups=groups)
    wall = time.perf_counter() - started
    placement = {a["course_id"]: (a["venue_id"], a["slot_id"]) for a in result.assignments}
    quality = metrics_mod.score(ctx, placement)["score"] if placement else None
    violations = verify(result.assignments, courses, faculty, venues, slots,
                        groups, ctx=ctx) if result.assignments else ["no assignments"]
    durations = sorted({c["duration_minutes"] for c in courses})
    optimizer = result.engine.get("optimizer") or {}
    return {
        "sessions": n_sessions,
        "teachers": len(faculty),
        "rooms": len(venues),
        "durations": durations,
        "wall_s": round(wall, 2),
        "status": result.status,
        "path": result.engine.get("path"),
        "scheduled": len(result.assignments),
        "quality": quality,
        "improved": optimizer.get("improved"),
        "optimizer_budget_s": optimizer.get("budget_s"),
        "violations": len(violations),
        "sample_violation": violations[:1],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", type=int, nargs="+", default=[150, 400, 800])
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    rows = [run(args.seed, n) for n in args.sessions]
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        print(f"{'sessions':>9} {'teachers':>9} {'wall':>7} {'status':>9} {'path':>10} "
              f"{'scheduled':>10} {'quality':>8} {'opt_impr':>9} {'viol':>5}")
        for r in rows:
            print(f"{r['sessions']:>9} {r['teachers']:>9} {r['wall_s']:>7} "
                  f"{r['status']:>9} {r['path']:>10} {r['scheduled']:>10} "
                  f"{str(r['quality']):>8} {str(r['improved']):>9} {r['violations']:>5}")
            if r["violations"]:
                print("   ", r["sample_violation"])
    return 0 if all(r["violations"] == 0 for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
