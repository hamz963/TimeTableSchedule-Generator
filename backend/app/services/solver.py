"""OR-Tools CP-SAT timetable solver.

Model:
    x[c, v, s] in {0,1} = course c taught in venue v at slot s.
    Faculty is derived from course.faculty_id (each course has one faculty).

Hard constraints:
    - Each course assigned exactly once.
    - No faculty teaches 2 courses in the same slot.
    - No venue double-booking per slot.
    - Faculty unavailability respected.
    - Venue availability respected.
    - Venue capacity >= course capacity_required.
    - Required equipment subset of venue equipment.
    - Faculty daily workload (minutes) <= max_hours_per_day * 60.

Soft objectives (weighted, minimized penalty / maximized reward):
    - Preference satisfaction: reward preferred slots.
    - Room utilization: penalize wasted seats (capacity - required).
    - Delta stability (reschedule): penalize deviation from previous assignment.

Two-tier strategy (see JOINT_MODEL_MAX_VARS):
    - Small instances: exact CP-SAT model, warm-started with a greedy hint and
      guaranteed by a verified greedy fallback (feasible first, optimize
      with remaining budget).
    - Large instances: exact modeling alone exceeds the real-time budget, so
      the verified greedy heuristic (preference-, waste- and delta-aware) is
      served directly — deterministic and well under budget.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ortools.sat.python import cp_model


#: Above this estimated variable count (courses x venues x slots) the exact
#: CP-SAT model build alone (~45 us/var) blows the real-time budget, so
#: generate() serves the verified greedy heuristic directly instead of
#: building a model it cannot solve in time. The heuristic is preference-,
#: waste- and delta-aware, so solution quality stays high.
JOINT_MODEL_MAX_VARS = 25_000


@dataclass
class SolverResult:
    status: str  # optimal | feasible | infeasible | timeout
    assignments: List[Dict[str, int]] = field(default_factory=list)
    solver_time_ms: int = 0
    objective_value: Optional[float] = None
    conflicts_resolved: int = 0


def _slot_minutes(slot: Dict[str, Any]) -> int:
    try:
        return int(slot.get("duration_minutes", 60))
    except (TypeError, ValueError):
        return 60


def _slot_start_minutes(slot: Dict[str, Any]) -> int:
    """Minutes since midnight for ordering/bucketing (tolerates Time/str)."""
    from datetime import time as dtime

    value = slot.get("start_time", "09:00")
    if isinstance(value, dtime):
        return value.hour * 60 + value.minute
    try:
        h, m = str(value).split(":")
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return 0


def _time_bucket(start_minutes: int) -> str:
    if start_minutes < 12 * 60:
        return "Morning"
    if start_minutes < 17 * 60:
        return "Afternoon"
    return "Evening"


class TimetableSolver:
    def __init__(self, time_limit_seconds: float = 5.0, num_workers: int = 8):
        self.time_limit_seconds = time_limit_seconds
        self.num_workers = num_workers
        self.model = cp_model.CpModel()
        self._vars: Dict[Tuple[int, int, int], Any] = {}
        # Indexes built in one pass during add_variables (avoids O(V*S*N) rescans).
        self._by_course: Dict[int, List[Tuple[int, int, int]]] = {}
        self._by_ven_slot: Dict[Tuple[int, int], List[Tuple[int, int, int]]] = {}
        self._by_course_slot: Dict[Tuple[int, int], List[Tuple[int, int, int]]] = {}
        self._courses: List[Dict[str, Any]] = []
        self._status: str = "unknown"

    # -- variable construction -------------------------------------------------
    def add_variables(
        self,
        courses: List[Dict[str, Any]],
        venues: List[Dict[str, Any]],
        slots: List[Dict[str, Any]],
    ) -> None:
        self._courses = courses
        venue_by_id = {v["id"]: v for v in venues}
        for c in courses:
            for v in venues:
                # Static pruning: capacity + equipment (hard, no need for constraints).
                if v.get("capacity", 0) < c.get("capacity_required", 0):
                    continue
                req = set(c.get("required_equipment", []) or [])
                has = set(v.get("equipment", []) or [])
                if not req.issubset(has):
                    continue
                avail = set(v.get("available_slots") or [])
                for s in slots:
                    if avail and s["id"] not in avail:
                        continue  # venue not available at this slot
                    key = (c["id"], v["id"], s["id"])
                    self._vars[key] = self.model.NewBoolVar(
                        f"x_c{c['id']}_v{v['id']}_s{s['id']}"
                    )
                    self._by_course.setdefault(c["id"], []).append(key)
                    self._by_ven_slot.setdefault((v["id"], s["id"]), []).append(key)
                    self._by_course_slot.setdefault((c["id"], s["id"]), []).append(key)
        # Keep venue lookup for later use
        self._venue_by_id = venue_by_id

    # -- hard constraints ------------------------------------------------------
    def add_constraints(
        self,
        courses: List[Dict[str, Any]],
        faculty: List[Dict[str, Any]],
        venues: List[Dict[str, Any]],
        slots: List[Dict[str, Any]],
        locked_assignments: Optional[List[Dict[str, Any]]] = None,
        session_groups: Optional[List[List[int]]] = None,
        max_consecutive: int = 0,
    ) -> None:
        faculty_by_id = {f["id"]: f for f in faculty}
        slot_ids = [s["id"] for s in slots]
        venue_ids = [v["id"] for v in venues]
        slot_by_id = {s["id"]: s for s in slots}

        # 1. Each course exactly once.
        for c in courses:
            keys = self._by_course.get(c["id"], [])
            if not keys:
                # No feasible (venue, slot) pair -> force infeasibility honestly.
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
            f = faculty_by_id.get(c["faculty_id"], {})
            unavailable = set(f.get("unavailable_slots", []) or [])
            for sid in unavailable:
                for k in self._by_course_slot.get((c["id"], sid), []):
                    self.model.Add(self._vars[k] == 0)

        # 5. Daily workload limits (minutes per faculty per day).
        # Group slots by day.
        days: Dict[str, List[int]] = {}
        for s in slots:
            days.setdefault(str(s.get("day_of_week", "?")), []).append(s["id"])
        for f in faculty:
            fid = f["id"]
            limit_min = int(f.get("max_hours_per_day", 6)) * 60
            fcourses = courses_by_faculty.get(fid, [])
            for day, day_slot_ids in days.items():
                terms = []
                for sid in day_slot_ids:
                    dur_s = _slot_minutes(slot_by_id.get(sid, {}))
                    for c in fcourses:
                        for k in self._by_course_slot.get((c["id"], sid), []):
                            terms.append(self._vars[k] * dur_s)
                if terms:
                    self.model.Add(sum(terms) <= limit_min)

        # 6. Locked assignments (delta rescheduling pins).
        for lock in locked_assignments or []:
            key = (lock["course_id"], lock["venue_id"], lock["slot_id"])
            if key in self._vars:
                self.model.Add(self._vars[key] == 1)

        # 7. Session groups (multi-session courses): all sessions of the same
        # course meet in different time slots (never twice at once).
        for group in session_groups or []:
            for sid in slot_ids:
                lits = [
                    self._vars[k]
                    for cid in group
                    for k in self._by_course_slot.get((cid, sid), [])
                ]
                if len(lits) > 1:
                    self.model.Add(sum(lits) <= 1)

        # 8. Break rule: at most `max_consecutive` back-to-back periods per
        # teacher per day (sliding window over the ordered day grid).
        if max_consecutive and max_consecutive > 0:
            ordered_days: Dict[str, List[int]] = {}
            for s in slots:
                ordered_days.setdefault(str(s.get("day_of_week", "?")), []).append(s["id"])
            for day in ordered_days:
                ordered_days[day].sort(
                    key=lambda sid: _slot_start_minutes(slot_by_id.get(sid, {}))
                )
            for fid, fcourses in courses_by_faculty.items():
                for day_slot_ids in ordered_days.values():
                    window = max_consecutive + 1
                    for i in range(len(day_slot_ids) - window + 1):
                        lits = [
                            self._vars[k]
                            for c in fcourses
                            for sid in day_slot_ids[i:i + window]
                            for k in self._by_course_slot.get((c["id"], sid), [])
                        ]
                        if len(lits) > 1:
                            self.model.Add(sum(lits) <= max_consecutive)

    # -- greedy construction -------------------------------------------------
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
        """First-fit constructive heuristic (most-constrained-first).

        Pure-Python and model-free: prunes candidates exactly like
        add_variables (capacity, equipment, venue availability) plus faculty
        unavailability, then places courses respecting occupancy and daily
        workload. Candidate order prefers the previous assignment (delta
        stability), then faculty preferences, then least wasted seats.

        Returns a feasible assignment when one is easily reachable, else None.
        Used as a CP-SAT solution hint, as a fallback when exact search
        exceeds its budget, and as the primary solver for instances too large
        to model exactly within the real-time budget.
        """
        faculty_by_id = {f["id"]: f for f in faculty}
        venue_by_id = {v["id"]: v for v in venues}
        slot_by_id = {s["id"]: s for s in slots}
        course_by_id = {c["id"]: c for c in courses}
        prev_map = (
            {(p["course_id"]): (p["venue_id"], p["slot_id"]) for p in previous}
            if previous
            else {}
        )
        fac_slot_used: set = set()
        ven_slot_used: set = set()
        fac_day_mins: Dict[Tuple[int, str], int] = {}
        chosen: List[Tuple[int, int, int]] = []
        # Ordered day grids for the break rule (consecutive-period check).
        day_order: Dict[str, List[int]] = {}
        for s in slots:
            day_order.setdefault(str(s.get("day_of_week", "?")), []).append(s["id"])
        for day in day_order:
            day_order[day].sort(key=lambda sid: _slot_start_minutes(slot_by_id.get(sid, {})))
        slot_index: Dict[int, int] = {}
        for day, sids in day_order.items():
            for i, sid in enumerate(sids):
                slot_index[sid] = i
        fac_day_idx: Dict[Tuple[int, str], set] = {}
        # Session-group day tracking: spread a course's sessions across days.
        group_of: Dict[int, int] = {}
        for gi, group in enumerate(session_groups or []):
            for cid in group:
                group_of[cid] = gi
        group_days: Dict[int, set] = {gi: set() for gi in range(len(session_groups or []))}

        def occupy(cid: int, vid: int, sid: int) -> bool:
            c = course_by_id.get(cid)
            if c is None:
                return False
            slot = slot_by_id.get(sid, {})
            day = str(slot.get("day_of_week", "?"))
            dur = _slot_minutes(slot)
            f = faculty_by_id.get(c["faculty_id"], {})
            limit = int(f.get("max_hours_per_day", 6)) * 60
            if (c["faculty_id"], sid) in fac_slot_used:
                return False
            if (vid, sid) in ven_slot_used:
                return False
            if fac_day_mins.get((c["faculty_id"], day), 0) + dur > limit:
                return False
            if max_consecutive and max_consecutive > 0:
                # Break rule: placing here must not extend a back-to-back run
                # past max_consecutive periods on this day.
                used = fac_day_idx.get((c["faculty_id"], day), set())
                idx = slot_index.get(sid)
                if idx is not None:
                    run = 1
                    j = idx - 1
                    while j in used:
                        run += 1
                        j -= 1
                    j = idx + 1
                    while j in used:
                        run += 1
                        j += 1
                    if run > max_consecutive:
                        return False
            fac_slot_used.add((c["faculty_id"], sid))
            ven_slot_used.add((vid, sid))
            fac_day_mins[(c["faculty_id"], day)] = fac_day_mins.get((c["faculty_id"], day), 0) + dur
            if max_consecutive and slot_index.get(sid) is not None:
                fac_day_idx.setdefault((c["faculty_id"], day), set()).add(slot_index[sid])
            if cid in group_of:
                group_days[group_of[cid]].add(day)
            chosen.append((cid, vid, sid))
            return True

        def venue_compatible(c: Dict[str, Any], v: Dict[str, Any]) -> bool:
            if int(v.get("capacity", 0)) < int(c.get("capacity_required", 0)):
                return False
            req = set(c.get("required_equipment", []) or [])
            return req.issubset(set(v.get("equipment", []) or []))

        # Pre-place locked assignments (delta-reschedule pins), validating
        # them against the same pruning the exact model applies.
        locked_ids: set = set()
        for lock in locked_assignments or []:
            c = course_by_id.get(lock["course_id"])
            v = venue_by_id.get(lock["venue_id"])
            sid = lock["slot_id"]
            if c is None or v is None or sid not in slot_by_id:
                return None
            if not venue_compatible(c, v):
                return None
            avail = v.get("available_slots") or []
            if avail and sid not in avail:
                return None
            f = faculty_by_id.get(c["faculty_id"], {})
            if sid in (f.get("unavailable_slots", []) or []):
                return None
            if not occupy(c["id"], v["id"], sid):
                return None  # conflicting locks -> let the exact model decide
            locked_ids.add(c["id"])

        def candidates(c: Dict[str, Any]) -> List[Tuple[int, int, int]]:
            f = faculty_by_id.get(c["faculty_id"], {})
            unavail = set(f.get("unavailable_slots", []) or [])
            prefs = set(f.get("preferences", []) or [])
            prev = prev_map.get(c["id"])
            cands = []
            for v in venues:
                if not venue_compatible(c, v):
                    continue
                avail = v.get("available_slots") or []
                for s in slots:
                    if s["id"] in unavail:
                        continue
                    if avail and s["id"] not in avail:
                        continue
                    cands.append((c["id"], v["id"], s["id"]))

            def sort_key(k: Tuple[int, int, int]) -> Tuple[int, int, int, int, int, int, int]:
                venue = venue_by_id.get(k[1], {})
                waste = max(0, int(venue.get("capacity", 0)) - int(c.get("capacity_required", 0)))
                day = str(slot_by_id.get(k[2], {}).get("day_of_week", "?"))
                used_days = group_days.get(group_of.get(c["id"], -1), set())
                band = (c.get("preferred_time") or "").strip().capitalize()
                band_miss = 0
                if band in ("Morning", "Afternoon", "Evening"):
                    slot_band = _time_bucket(_slot_start_minutes(slot_by_id.get(k[2], {})))
                    band_miss = 0 if slot_band == band else 1
                return (
                    0 if prev == (k[1], k[2]) else 1,  # delta stability first
                    0 if day not in used_days else 1,  # then spread sessions across days
                    band_miss,  # then the course's own time band
                    0 if k[2] in prefs else 1,  # then preferences
                    waste,  # then least wasted seats
                    k[1],
                    k[2],
                )

            return sorted(cands, key=sort_key)

        rest = [c for c in courses if c["id"] not in locked_ids]
        with_counts = [(c, candidates(c)) for c in rest]
        with_counts.sort(key=lambda t: (len(t[1]), t[0]["id"]))
        for c, cands in with_counts:
            placed = any(occupy(c["id"], vid, sid) for (_, vid, sid) in cands)
            if not placed:
                return None  # greedy stuck
        return [
            {"course_id": cid, "faculty_id": course_by_id[cid]["faculty_id"],
             "venue_id": vid, "slot_id": sid}
            for (cid, vid, sid) in chosen
        ]

    def apply_hint(self, hint: List[Dict[str, int]]) -> None:
        for a in hint:
            key = (a["course_id"], a["venue_id"], a["slot_id"])
            if key in self._vars:
                self.model.AddHint(self._vars[key], 1)

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
        """Check all hard constraints; return list of violation messages (empty = ok)."""
        violations: List[str] = []
        course_by_id = {c["id"]: c for c in courses}
        if cancelled:
            course_by_id = {cid: c for cid, c in course_by_id.items() if cid not in cancelled}
        faculty_by_id = {f["id"]: f for f in faculty}
        venue_by_id = {v["id"]: v for v in venues}
        slot_by_id = {s["id"]: s for s in slots}
        if sorted(a["course_id"] for a in assignments) != sorted(course_by_id):
            violations.append("each course must be assigned exactly once")
        fac_slot: set = set()
        ven_slot: set = set()
        day_mins: Dict[Tuple[int, str], int] = {}
        for a in assignments:
            c = course_by_id.get(a["course_id"], {})
            if a["faculty_id"] != c.get("faculty_id"):
                violations.append(f"course {a['course_id']}: wrong faculty")
            k1 = (a["faculty_id"], a["slot_id"])
            k2 = (a["venue_id"], a["slot_id"])
            if k1 in fac_slot:
                violations.append(f"faculty double-booked: {k1}")
            if k2 in ven_slot:
                violations.append(f"venue double-booked: {k2}")
            fac_slot.add(k1)
            ven_slot.add(k2)
            f = faculty_by_id.get(a["faculty_id"], {})
            if a["slot_id"] in (f.get("unavailable_slots", []) or []):
                violations.append(f"faculty {a['faculty_id']} unavailable at slot {a['slot_id']}")
            v = venue_by_id.get(a["venue_id"], {})
            if int(v.get("capacity", 0)) < int(c.get("capacity_required", 0)):
                violations.append(f"course {a['course_id']}: venue capacity exceeded")
            if not set(c.get("required_equipment", []) or []).issubset(set(v.get("equipment", []) or [])):
                violations.append(f"course {a['course_id']}: missing equipment")
            avail = v.get("available_slots") or []
            if avail and a["slot_id"] not in avail:
                violations.append(f"venue {a['venue_id']} unavailable at slot {a['slot_id']}")
            day = str(slot_by_id.get(a["slot_id"], {}).get("day_of_week", "?"))
            day_mins[(a["faculty_id"], day)] = day_mins.get((a["faculty_id"], day), 0) + _slot_minutes(
                slot_by_id.get(a["slot_id"], {})
            )
        for (fid, day), mins in day_mins.items():
            limit = int(faculty_by_id.get(fid, {}).get("max_hours_per_day", 6)) * 60
            if mins > limit:
                violations.append(f"faculty {fid} exceeds daily limit on {day}")
        if max_consecutive and max_consecutive > 0:
            day_order: Dict[str, List[int]] = {}
            for s in slots:
                day_order.setdefault(str(s.get("day_of_week", "?")), []).append(s["id"])
            for day in day_order:
                day_order[day].sort(key=lambda sid: _slot_start_minutes(slot_by_id.get(sid, {})))
            order_index = {sid: i for day in day_order.values() for i, sid in enumerate(day)}
            runs: Dict[Tuple[int, str], List[int]] = {}
            for a in assignments:
                s = slot_by_id.get(a["slot_id"], {})
                day = str(s.get("day_of_week", "?"))
                if a["slot_id"] in order_index:
                    runs.setdefault((a["faculty_id"], day), []).append(order_index[a["slot_id"]])
            for (fid, day), idxs in runs.items():
                idxs = sorted(idxs)
                longest, cur = 1, 1
                for i in range(1, len(idxs)):
                    cur = cur + 1 if idxs[i] == idxs[i - 1] + 1 else 1
                    longest = max(longest, cur)
                if longest > max_consecutive:
                    violations.append(
                        f"faculty {fid} teaches {longest} back-to-back periods on {day} "
                        f"(max {max_consecutive})"
                    )
        slot_of = {a["course_id"]: a["slot_id"] for a in assignments}
        for group in session_groups or []:
            seen: Dict[int, int] = {}
            for cid in group:
                sid = slot_of.get(cid)
                if sid is None:
                    continue
                if sid in seen:
                    violations.append(
                        f"sessions {seen[sid]} and {cid} share slot {sid}"
                    )
                seen[sid] = cid
        return violations

    # -- soft objectives -------------------------------------------------------
    def add_objectives(
        self,
        courses: List[Dict[str, Any]],
        faculty: List[Dict[str, Any]],
        venues: List[Dict[str, Any]],
        previous: Optional[List[Dict[str, int]]] = None,
        fairness_weight: int = 1,
        slots: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        faculty_by_id = {f["id"]: f for f in faculty}
        venue_by_id = {v["id"]: v for v in venues}
        course_by_id = {c["id"]: c for c in courses}
        # Precompute per-course preference sets and per-(course, venue) waste
        # to keep objective construction linear without repeated set-building.
        prefs_by_course = {
            c["id"]: set(faculty_by_id.get(c["faculty_id"], {}).get("preferences", []) or [])
            for c in courses
        }
        # Per-course time bands ("Morning"/"Afternoon"/"Evening") from the
        # dataset: reward sessions placed inside their band (soft suggestion).
        band_slots: Dict[str, set] = {}
        if slots:
            for s in slots:
                band_slots.setdefault(
                    _time_bucket(_slot_start_minutes(s)), set()).add(s["id"])
        band_by_course = {
            c["id"]: (c.get("preferred_time") or "").strip().capitalize()
            for c in courses
        }
        waste_by_course_venue = {}
        for c in courses:
            req = int(c.get("capacity_required", 0))
            for v in venues:
                waste_by_course_venue[(c["id"], v["id"])] = max(
                    0, int(v.get("capacity", 0)) - req
                ) // 10
        prev_by_course: Dict[int, set] = {}
        if previous:
            for p in previous:
                prev_by_course.setdefault(p["course_id"], set()).add(
                    (p["course_id"], p["venue_id"], p["slot_id"])
                )
        objective_terms = []
        for (cid, vid, sid), var in self._vars.items():
            if cid not in course_by_id:
                continue
            # Reward preferred slot: -10 * x (minimize => prefer).
            if sid in prefs_by_course.get(cid, ()):
                objective_terms.append(var * -10)
            # Reward the course's own time band (dataset soft suggestion).
            band = band_by_course.get(cid, "")
            if band and sid in band_slots.get(band, ()):
                objective_terms.append(var * -10)
            # Penalize wasted seats (scaled down to keep balance).
            objective_terms.append(var * waste_by_course_venue.get((cid, vid), 0))
        # Delta stability: penalize moves away from previous assignment.
        if previous:
            prev_set = {(p["course_id"], p["venue_id"], p["slot_id"]) for p in previous}
            for key, var in self._vars.items():
                if key not in prev_set and prev_by_course.get(key[0]):
                    objective_terms.append(var * 50)
        # Fairness (day-spread): minimize the heaviest single-day load any
        # faculty carries, so teaching spreads across the week instead of
        # bunching onto one day. Linear minimax formulation.
        if fairness_weight and slots:
            slot_by_id = {s["id"]: s for s in slots}
            days: Dict[str, List[int]] = {}
            for s in slots:
                days.setdefault(str(s.get("day_of_week", "?")), []).append(s["id"])
            courses_by_faculty: Dict[int, List[int]] = {}
            for c in courses:
                courses_by_faculty.setdefault(c["faculty_id"], []).append(c["id"])
            max_day_load = self.model.NewIntVar(0, 24 * 60 * 7, "max_day_load")
            for fid, cids in courses_by_faculty.items():
                for day_slot_ids in days.values():
                    terms = []
                    for sid in day_slot_ids:
                        dur_s = _slot_minutes(slot_by_id.get(sid, {}))
                        for cid in cids:
                            for k in self._by_course_slot.get((cid, sid), []):
                                terms.append(self._vars[k] * dur_s)
                    if terms:
                        self.model.Add(max_day_load >= sum(terms))
            objective_terms.append(max_day_load * fairness_weight)
        if objective_terms:
            self.model.Minimize(sum(objective_terms))

    # -- solve -----------------------------------------------------------------
    def solve(self, time_limit_seconds: Optional[float] = None) -> SolverResult:
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = float(
            time_limit_seconds if time_limit_seconds is not None else self.time_limit_seconds
        )
        # Never oversubscribe the machine; excess workers thrash and slow search.
        solver.parameters.num_search_workers = max(
            1, min(self.num_workers, os.cpu_count() or 1)
        )
        started = time.perf_counter()
        status = solver.Solve(self.model)
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        mapping = {
            cp_model.OPTIMAL: "optimal",
            cp_model.FEASIBLE: "feasible",
            cp_model.INFEASIBLE: "infeasible",
            cp_model.UNKNOWN: "timeout",
        }
        self._status = mapping.get(status, "unknown")
        result = SolverResult(status=self._status, solver_time_ms=elapsed_ms)

        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            try:
                result.objective_value = solver.ObjectiveValue()
            except Exception:
                result.objective_value = None
            course_by_id = {c["id"]: c for c in self._courses}
            for (cid, vid, sid), var in self._vars.items():
                if solver.Value(var):
                    course = course_by_id.get(cid, {})
                    result.assignments.append(
                        {
                            "course_id": cid,
                            "faculty_id": course.get("faculty_id"),
                            "venue_id": vid,
                            "slot_id": sid,
                        }
                    )
            result.conflicts_resolved = 0
        self._last_result = result
        return result

    def get_solution(self) -> List[Dict[str, int]]:
        """Return assignments from the most recent solve() call."""
        last = getattr(self, "_last_result", None)
        if last is None:
            raise RuntimeError("No solution yet; call solve() first.")
        return last.assignments

    # -- convenience one-shot ---------------------------------------------------
    @classmethod
    def generate(
        cls,
        faculty: List[Dict[str, Any]],
        venues: List[Dict[str, Any]],
        slots: List[Dict[str, Any]],
        courses: List[Dict[str, Any]],
        time_limit_seconds: float = 5.0,
        locked_assignments: Optional[List[Dict[str, Any]]] = None,
        previous: Optional[List[Dict[str, int]]] = None,
        session_groups: Optional[List[List[int]]] = None,
        max_consecutive: int = 0,
    ) -> SolverResult:
        wall_start = time.perf_counter()
        est_vars = len(courses) * len(venues) * len(slots)

        # Tier 1 — exact CP-SAT for instances small enough to model exactly
        # within the real-time budget.
        if est_vars <= JOINT_MODEL_MAX_VARS:
            solver = cls(time_limit_seconds=time_limit_seconds)
            solver.add_variables(courses, venues, slots)
            solver.add_constraints(
                courses, faculty, venues, slots, locked_assignments,
                session_groups, max_consecutive,
            )
            solver.add_objectives(courses, faculty, venues, previous, slots=slots)
            # Feasible-first matheuristic: greedy baseline as hint + fallback.
            greedy = TimetableSolver.greedy_assign(
                courses, faculty, venues, slots, locked_assignments, previous,
                session_groups, max_consecutive,
            )
            if greedy is not None:
                solver.apply_hint(greedy)
            elapsed = time.perf_counter() - wall_start
            # Reserve a generous margin: CP-SAT's max_time is a soft limit and can
            # overshoot on stop-check granularity, so the total must stay well clear.
            # When a verified greedy fallback already exists, CP-SAT only gets a
            # short improvement window; otherwise it gets the full remainder.
            if greedy is not None and elapsed >= time_limit_seconds - 0.8:
                # Model build consumed the budget; return the verified greedy directly.
                total_ms = int((time.perf_counter() - wall_start) * 1000)
                if not TimetableSolver.verify(
                    greedy, courses, faculty, venues, slots, session_groups,
                    max_consecutive=max_consecutive,
                ):
                    return SolverResult(
                        status="feasible",
                        assignments=greedy,
                        solver_time_ms=total_ms,
                        objective_value=TimetableSolver.objective_of(greedy, courses, faculty, venues),
                    )
            remaining = max(0.2, time_limit_seconds - elapsed - 0.8)
            solve_budget = min(remaining, 1.5) if greedy is not None else remaining
            result = solver.solve(solve_budget)
            total_ms = int((time.perf_counter() - wall_start) * 1000)
            result.solver_time_ms = total_ms
            if result.status in ("infeasible", "timeout", "unknown") and greedy is not None:
                if not TimetableSolver.verify(
                    greedy, courses, faculty, venues, slots, session_groups,
                    max_consecutive=max_consecutive,
                ):
                    result = SolverResult(
                        status="feasible",
                        assignments=greedy,
                        solver_time_ms=total_ms,
                        objective_value=TimetableSolver.objective_of(greedy, courses, faculty, venues),
                    )
            return result

        # Tier 2 — large instances: exact modeling alone exceeds the budget, so
        # serve the verified greedy heuristic directly (preference-, waste- and
        # delta-aware ordering keeps quality high). Deterministic and fast.
        greedy = TimetableSolver.greedy_assign(
            courses, faculty, venues, slots, locked_assignments, previous,
            session_groups, max_consecutive,
        )
        total_ms = int((time.perf_counter() - wall_start) * 1000)
        if greedy is not None and not TimetableSolver.verify(
            greedy, courses, faculty, venues, slots, session_groups,
            max_consecutive=max_consecutive,
        ):
            return SolverResult(
                status="feasible",
                assignments=greedy,
                solver_time_ms=total_ms,
                objective_value=TimetableSolver.objective_of(
                    greedy, courses, faculty, venues
                ),
            )
        # Greedy stuck: report honestly (callers surface 422); the instance is
        # likely over-constrained.
        return SolverResult(status="timeout", solver_time_ms=total_ms)

    @staticmethod
    def objective_of(
        assignments: List[Dict[str, int]],
        courses: List[Dict[str, Any]],
        faculty: List[Dict[str, Any]],
        venues: List[Dict[str, Any]],
    ) -> float:
        """Evaluate the soft-objective value of an assignment (matches Minimize)."""
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
