"""Problem context: the single source of truth for a timetable instance.

Every derived structure (day ordering, slot lookups, time buckets, occupancy
keys, session-group membership) is computed exactly once here and shared by
the heuristic constructor, the metaheuristic optimizer, the hard-constraint
verifier and the metrics modules. This replaces the earlier design where each
consumer rebuilt the same lookups independently.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time as dtime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

DAY_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

#: A placement is one scheduled session: course -> (faculty, venue, slot).
Placement = Dict[str, int]


def slot_minutes(slot: Dict[str, Any]) -> int:
    """Duration of a slot in minutes (tolerant of bad input)."""
    try:
        return int(slot.get("duration_minutes", 60))
    except (TypeError, ValueError):
        return 60


def slot_start_minutes(slot: Dict[str, Any]) -> int:
    """Minutes since midnight for ordering/bucketing (tolerates Time/str)."""
    value = slot.get("start_time", "09:00")
    if isinstance(value, dtime):
        return value.hour * 60 + value.minute
    try:
        h, m = str(value).split(":")
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return 0


def time_bucket(start_minutes: int) -> str:
    if start_minutes < 12 * 60:
        return "Morning"
    if start_minutes < 17 * 60:
        return "Afternoon"
    return "Evening"


@dataclass
class ProblemContext:
    """Normalized instance with all derived indexes precomputed."""

    faculty: List[Dict[str, Any]]
    venues: List[Dict[str, Any]]
    slots: List[Dict[str, Any]]
    courses: List[Dict[str, Any]]
    session_groups: List[List[int]] = field(default_factory=list)
    locked_assignments: List[Dict[str, Any]] = field(default_factory=list)
    max_consecutive: int = 0
    rules: List[Any] = field(default_factory=list)

    # -- derived (filled in __post_init__) ------------------------------------
    faculty_by_id: Dict[int, Dict[str, Any]] = field(default_factory=dict, repr=False)
    venue_by_id: Dict[int, Dict[str, Any]] = field(default_factory=dict, repr=False)
    slot_by_id: Dict[int, Dict[str, Any]] = field(default_factory=dict, repr=False)
    course_by_id: Dict[int, Dict[str, Any]] = field(default_factory=dict, repr=False)
    days: List[str] = field(default_factory=list, repr=False)
    slot_ids_by_day: Dict[str, List[int]] = field(default_factory=dict, repr=False)
    slot_index: Dict[int, int] = field(default_factory=dict, repr=False)
    slot_day: Dict[int, str] = field(default_factory=dict, repr=False)
    slot_start: Dict[int, int] = field(default_factory=dict, repr=False)
    slot_dur: Dict[int, int] = field(default_factory=dict, repr=False)
    band_slots: Dict[str, Set[int]] = field(default_factory=dict, repr=False)
    courses_by_faculty: Dict[int, List[Dict[str, Any]]] = field(default_factory=dict, repr=False)
    faculty_unavailable: Dict[int, Set[int]] = field(default_factory=dict, repr=False)
    venue_allowed: Dict[int, Set[int]] = field(default_factory=dict, repr=False)
    group_of: Dict[int, int] = field(default_factory=dict, repr=False)
    group_members: Dict[int, List[int]] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self.faculty_by_id = {f["id"]: f for f in self.faculty}
        self.venue_by_id = {v["id"]: v for v in self.venues}
        self.slot_by_id = {s["id"]: s for s in self.slots}
        self.course_by_id = {c["id"]: c for c in self.courses}

        ordered = sorted(
            self.slots,
            key=lambda s: (
                DAY_ORDER.index(s["day_of_week"])
                if s.get("day_of_week") in DAY_ORDER else 99,
                slot_start_minutes(s),
                s["id"],
            ),
        )
        for s in ordered:
            day = str(s.get("day_of_week", "?"))
            self.slot_ids_by_day.setdefault(day, []).append(s["id"])
            self.slot_day[s["id"]] = day
            self.slot_start[s["id"]] = slot_start_minutes(s)
            self.slot_dur[s["id"]] = slot_minutes(s)
            self.band_slots.setdefault(time_bucket(self.slot_start[s["id"]]), set()).add(s["id"])
        self.days = list(self.slot_ids_by_day.keys())
        for day, sids in self.slot_ids_by_day.items():
            sids.sort(key=lambda sid: self.slot_start.get(sid, 0))
            for i, sid in enumerate(sids):
                self.slot_index[sid] = i

        for c in self.courses:
            self.courses_by_faculty.setdefault(c["faculty_id"], []).append(c)
        for f in self.faculty:
            self.faculty_unavailable[f["id"]] = set(f.get("unavailable_slots", []) or [])
        for v in self.venues:
            avail = v.get("available_slots") or []
            if avail:
                self.venue_allowed[v["id"]] = set(avail)

        for gi, group in enumerate(self.session_groups or []):
            self.group_members[gi] = list(group)
            for cid in group:
                self.group_of[cid] = gi

    # -- convenience ----------------------------------------------------------
    def faculty_ids(self) -> Set[int]:
        return set(self.faculty_by_id)

    def new_placements(self) -> Dict[int, Tuple[int, int]]:
        """Mutable state for the optimizer: course_id -> (venue_id, slot_id)."""
        return {}

    def empty(self) -> bool:
        return not self.courses

    def day_index_of(self, slot_id: int) -> int:
        day = self.slot_day.get(slot_id, "?")
        return DAY_ORDER.index(day) if day in DAY_ORDER else 99

    def ordered_slot_position(self, slot_id: int) -> Tuple[int, int]:
        """Global (day, start) ordering key used to compare 'before' relations."""
        return (self.day_index_of(slot_id), self.slot_start.get(slot_id, 0))

    # -- user-rule hooks (declarative constraints drive the solver) ------------
    def fits_in_slot(self, cid: int, sid: int) -> bool:
        """True when the session actually fits the time block.

        A 2-hour lab cannot sit in a 1-hour slot: without this check the model
        happily scheduled multi-hour sessions into short blocks, because the
        course duration was only ever used for workload accounting.
        """
        course = self.course_by_id.get(cid, {})
        need = int(course.get("duration_minutes", 0) or 0)
        if need <= 0:
            return True
        return self.slot_dur.get(sid, need) >= need

    def placement_allowed(self, cid: int, vid: int, sid: int) -> bool:
        """True when the session fits the slot and every hard rule permits it."""
        if not self.fits_in_slot(cid, sid):
            return False
        for rule in self.rules:
            if getattr(rule, "hard", True) and not rule.placement_allowed(self, cid, vid, sid):
                return False
        return True

    def move_allowed(
        self, cid: int, vid: int, sid: int, placement: Dict[int, Tuple[int, int]]
    ) -> bool:
        """True when every hard rule permits placing cid here given the rest."""
        for rule in self.rules:
            if getattr(rule, "hard", True) and not rule.move_ok(self, cid, vid, sid, placement):
                return False
        return True

    def rule_penalty(self, placement: Dict[int, Tuple[int, int]]) -> float:
        return sum(rule.penalty(self, placement) for rule in self.rules)

    def rule_violations(self, placement: Dict[int, Tuple[int, int]]) -> List[str]:
        out: List[str] = []
        for rule in self.rules:
            if getattr(rule, "hard", True):
                out.extend(rule.full_check(self, placement))
        return out

    @property
    def hard_rules(self) -> List[Any]:
        return [r for r in self.rules if getattr(r, "hard", True)]

    def rules_need_search(self) -> bool:
        """True when a hard rule can't be compiled into CP-SAT exactly."""
        for rule in self.rules:
            if not getattr(rule, "hard", True):
                continue
            kind = getattr(rule, "kind", "")
            if kind not in (
                "forbid_slot", "fixed_slot", "course_before", "same_day", "no_same_day",
            ):
                return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "courses": len(self.courses),
            "faculty": len(self.faculty),
            "venues": len(self.venues),
            "slots": len(self.slots),
            "days": self.days,
            "session_groups": len(self.session_groups),
            "rules": len(self.rules),
        }


def build_context(
    faculty: List[Dict[str, Any]],
    venues: List[Dict[str, Any]],
    slots: List[Dict[str, Any]],
    courses: List[Dict[str, Any]],
    session_groups: Optional[List[List[int]]] = None,
    locked_assignments: Optional[List[Dict[str, Any]]] = None,
    max_consecutive: int = 0,
    rules: Optional[List[Any]] = None,
) -> ProblemContext:
    return ProblemContext(
        faculty=faculty,
        venues=venues,
        slots=slots,
        courses=courses,
        session_groups=session_groups or [],
        locked_assignments=locked_assignments or [],
        max_consecutive=max_consecutive,
        rules=rules or [],
    )
