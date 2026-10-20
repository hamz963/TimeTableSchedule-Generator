"""Declarative constraint registry — user rules that actually drive the solver.

Each :class:`Rule` exposes three hooks the engine calls:

    placement_allowed(ctx, cid, vid, sid)   hard, local (one session)
    move_ok(ctx, cid, vid, sid, placement)  hard, relational (vs other sessions)
    penalty(ctx, placement)                 soft cost for the optimizer
    full_check(ctx, placement)              hard audit for verification

Built-in kinds (:func:`rule_catalog` returns their schemas):

    forbid_slot      hard  a course/teacher/room may not use given slots or days
    fixed_slot       hard  pin a course to a slot (optionally a room)
    course_before    hard  every session of course A precedes every session of B
    same_day         hard  listed courses all meet on the same day
    no_same_day      hard  two courses never share a day
    preferred_day    soft  reward placing a course on given days
    spread_sessions  soft  reward spreading one course's sessions across days
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from app.engine.context import DAY_ORDER, ProblemContext


def _slot_order(ctx: ProblemContext) -> Dict[int, int]:
    """Map every slot id to its position in the week (index 0 = earliest)."""
    ordered = sorted((s["id"] for s in ctx.slots), key=ctx.ordered_slot_position)
    return {sid: i for i, sid in enumerate(ordered)}


def _by_course_slot(x: Dict[Any, Any]) -> Dict[Tuple[int, int], Any]:
    """Collapse ``x[(cid, vid, sid)]`` into one 0/1 expression per (course, slot)."""
    out: Dict[Tuple[int, int], Any] = {}
    for key, var in x.items():
        if not isinstance(key, tuple) or len(key) != 3:
            continue
        cid, _vid, sid = key
        out[(cid, sid)] = out.get((cid, sid), 0) + var
    return out


def _by_course_day(x: Dict[Any, Any], ctx: ProblemContext) -> Dict[Tuple[int, str], Any]:
    """Collapse variables into one 0/1 expression per (course, day)."""
    out: Dict[Tuple[int, str], Any] = {}
    for key, var in x.items():
        if not isinstance(key, tuple) or len(key) != 3:
            continue
        cid, _vid, sid = key
        day = ctx.slot_day.get(sid)
        if day is None:
            continue
        out[(cid, day)] = out.get((cid, day), 0) + var
    return out


class RuleError(ValueError):
    """Raised when a rule references unknown entities or is malformed."""


def _norm_day(value: str) -> Optional[str]:
    key = (value or "").strip().lower()[:3].capitalize()
    return key if key in DAY_ORDER else None


def _ids(value: Any) -> List[int]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [int(v) for v in value]
    return [int(value)]


@dataclass
class Rule:
    kind: str
    params: Dict[str, Any] = field(default_factory=dict)
    hard: bool = True
    weight: float = 1.0
    name: str = ""

    def __post_init__(self) -> None:  # noqa: D401 - overridden by subclasses
        """Subclasses parse/validate ``params`` here.

        This no-op must exist on the base dataclass: the generated ``__init__``
        only calls ``__post_init__`` when the *base* class defines it, so
        without it the subclass hooks would silently never run.
        """

    # -- hooks (overridden by subclasses) -------------------------------------
    def placement_allowed(self, ctx: ProblemContext, cid: int, vid: int, sid: int) -> bool:
        return True

    def move_ok(
        self,
        ctx: ProblemContext,
        cid: int,
        vid: int,
        sid: int,
        placement: Dict[int, Any],
    ) -> bool:
        return True

    def penalty(self, ctx: ProblemContext, placement: Dict[int, Any]) -> float:
        return 0.0

    def full_check(self, ctx: ProblemContext, placement: Dict[int, Any]) -> List[str]:
        return []

    def cp_compile(self, ctx: ProblemContext, model: Any, x: Dict[Any, Any]) -> bool:
        """Try to encode the rule into CP-SAT. Returns True when fully encoded."""
        return False

    def describe(self) -> str:
        return self.name or self.kind


# --------------------------------------------------------------------------- #
# Concrete rules
# --------------------------------------------------------------------------- #
class ForbidSlotRule(Rule):
    """A course, teacher, or room may not be scheduled in given slots/days."""

    def __post_init__(self) -> None:
        self.entity = (self.params.get("entity") or "course").lower()
        ids = _ids(self.params.get("id"))
        self.entity_ids = set(ids)
        self.slot_ids = set(_ids(self.params.get("slots")))
        self.days = {_norm_day(d) for d in (self.params.get("days") or [])}
        self.days.discard(None)
        if not self.entity_ids:
            raise RuleError("forbid_slot requires params.id")
        if self.entity not in ("course", "faculty", "teacher", "venue", "room"):
            raise RuleError(f"forbid_slot entity must be course/faculty/venue, got '{self.entity}'")

    def _matches(self, ctx: ProblemContext, cid: int, vid: int, sid: int) -> bool:
        ent = self.entity
        if ent == "course":
            return cid in self.entity_ids
        if ent in ("faculty", "teacher"):
            course = ctx.course_by_id.get(cid, {})
            return course.get("faculty_id") in self.entity_ids
        return vid in self.entity_ids

    def _slot_blocked(self, ctx: ProblemContext, sid: int) -> bool:
        if sid in self.slot_ids:
            return True
        return ctx.slot_day.get(sid) in self.days if self.days else False

    def placement_allowed(self, ctx, cid, vid, sid) -> bool:
        if not self._matches(ctx, cid, vid, sid):
            return True
        return not self._slot_blocked(ctx, sid)

    def full_check(self, ctx, placement) -> List[str]:
        out = []
        for cid, (vid, sid) in placement.items():
            if self._matches(ctx, cid, vid, sid) and self._slot_blocked(ctx, sid):
                out.append(f"rule '{self.describe()}': session {cid} uses a forbidden slot")
        return out

    def cp_compile(self, ctx, model, x) -> bool:
        for key, var in x.items():
            if not isinstance(key, tuple) or len(key) != 3:
                continue
            _c, _v, _s = key
            if self._matches(ctx, _c, _v, _s) and self._slot_blocked(ctx, _s):
                model.Add(var == 0)
        return True


class FixedSlotRule(Rule):
    """Pin a course to an exact slot (optionally an exact room)."""

    def __post_init__(self) -> None:
        self.course_id = int(self.params.get("course_id"))
        self.slot_id = int(self.params.get("slot_id"))
        self.venue_id = self.params.get("venue_id")
        self.venue_id = int(self.venue_id) if self.venue_id is not None else None

    def placement_allowed(self, ctx, cid, vid, sid) -> bool:
        if cid != self.course_id:
            return True
        if sid != self.slot_id:
            return False
        return self.venue_id is None or vid == self.venue_id

    def full_check(self, ctx, placement) -> List[str]:
        got = placement.get(self.course_id)
        if got is None:
            return []
        if got[1] != self.slot_id or (self.venue_id is not None and got[0] != self.venue_id):
            return [f"rule '{self.describe()}': session {self.course_id} not at its fixed slot"]
        return []

    def cp_compile(self, ctx, model, x) -> bool:
        for key, var in x.items():
            if not isinstance(key, tuple) or key[0] != self.course_id:
                continue
            ok = key[2] == self.slot_id and (self.venue_id is None or key[1] == self.venue_id)
            model.Add(var == (1 if ok else 0))
        return True


class CourseBeforeRule(Rule):
    """Every session in group A is scheduled before every session in group B.

    ``course_a`` / ``course_b`` accept a single id or a list of session ids, so
    a multi-session course (e.g. "Math (1/3)") maps to all of its sessions.
    """

    def __post_init__(self) -> None:
        self.a = set(_ids(self.params.get("course_a")))
        self.b = set(_ids(self.params.get("course_b")))
        if not self.a or not self.b:
            raise RuleError("course_before requires course_a and course_b")

    def move_ok(self, ctx, cid, vid, sid, placement) -> bool:
        if cid in self.a:
            pos = ctx.ordered_slot_position(sid)
            for other, (_v, osid) in placement.items():
                if other in self.b and not (pos < ctx.ordered_slot_position(osid)):
                    return False
        elif cid in self.b:
            pos = ctx.ordered_slot_position(sid)
            for other, (_v, osid) in placement.items():
                if other in self.a and not (ctx.ordered_slot_position(osid) < pos):
                    return False
        return True

    def full_check(self, ctx, placement) -> List[str]:
        a_slots = [placement[c][1] for c in self.a if c in placement]
        b_slots = [placement[c][1] for c in self.b if c in placement]
        if not a_slots or not b_slots:
            return []
        if not (max(ctx.ordered_slot_position(s) for s in a_slots)
                < min(ctx.ordered_slot_position(s) for s in b_slots)):
            return [f"rule '{self.describe()}': {sorted(self.a)} must precede {sorted(self.b)}"]
        return []

    def cp_compile(self, ctx, model, x) -> bool:
        """Every session of A strictly before every session of B.

        For each (a, b) pair and each candidate slot of ``a``: "a sits here"
        implies "b is not in this slot or any earlier one". Linear, no
        quadratic terms, and it matches ``full_check`` exactly.
        """
        order = _slot_order(ctx)
        if not order:
            return True
        per_slot = _by_course_slot(x)
        slots = sorted(order, key=order.get)
        for a in self.a:
            for b in self.b:
                for sa in slots:
                    here = per_slot.get((a, sa))
                    if here is None:
                        continue
                    earlier_b = [per_slot[(b, sb)] for sb in slots
                                 if order[sb] <= order[sa] and (b, sb) in per_slot]
                    terms = [here, *earlier_b]
                    if len(terms) > 1:
                        model.Add(sum(terms) <= 1)
        return True


class SameDayRule(Rule):
    """All listed sessions meet on the same day."""

    def __post_init__(self) -> None:
        self.courses = set(_ids(self.params.get("courses")))
        if len(self.courses) < 2:
            raise RuleError("same_day requires at least two session ids")

    def full_check(self, ctx, placement) -> List[str]:
        days = {ctx.slot_day.get(placement[c][1]) for c in self.courses if c in placement}
        if len(days) > 1:
            return [f"rule '{self.describe()}': {sorted(self.courses)} must share a day"]
        return []

    def move_ok(self, ctx, cid, vid, sid, placement) -> bool:
        if cid not in self.courses:
            return True
        day = ctx.slot_day.get(sid)
        for other in self.courses:
            if other == cid or other not in placement:
                continue
            if ctx.slot_day.get(placement[other][1]) != day:
                return False
        return True

    def cp_compile(self, ctx, model, x) -> bool:
        """All listed sessions share one day: equal per-day occupancy for every pair."""
        per_day = _by_course_day(x, ctx)
        members = [c for c in sorted(self.courses) if any((c, d) in per_day for d in ctx.days)]
        for day in ctx.days:
            for first, second in zip(members, members[1:]):
                ea, eb = per_day.get((first, day)), per_day.get((second, day))
                if ea is None and eb is None:
                    continue
                if ea is None:
                    model.Add(eb == 0)
                elif eb is None:
                    model.Add(ea == 0)
                else:
                    model.Add(ea == eb)
        return True


class NoSameDayRule(Rule):
    """Two session groups never share a day."""

    def __post_init__(self) -> None:
        self.a = set(_ids(self.params.get("course_a")))
        self.b = set(_ids(self.params.get("course_b")))
        if not self.a or not self.b:
            raise RuleError("no_same_day requires course_a and course_b")

    def move_ok(self, ctx, cid, vid, sid, placement) -> bool:
        day = ctx.slot_day.get(sid)
        others = self.b if cid in self.a else (self.a if cid in self.b else None)
        if others is None:
            return True
        for other in others:
            if other in placement and ctx.slot_day.get(placement[other][1]) == day:
                return False
        return True

    def full_check(self, ctx, placement) -> List[str]:
        for a in self.a:
            for b in self.b:
                if a in placement and b in placement:
                    if ctx.slot_day[placement[a][1]] == ctx.slot_day[placement[b][1]]:
                        return [f"rule '{self.describe()}': sessions {a} and {b} share a day"]
        return []

    def cp_compile(self, ctx, model, x) -> bool:
        """Two groups never share a day: at most one group occupies each day."""
        per_day = _by_course_day(x, ctx)
        for day in ctx.days:
            for a in self.a:
                for b in self.b:
                    ea, eb = per_day.get((a, day)), per_day.get((b, day))
                    if ea is None or eb is None:
                        continue
                    model.Add(ea + eb <= 1)
        return True


class PreferredDayRule(Rule):
    """Soft: reward placing a session on the given days."""

    def __post_init__(self) -> None:
        ids = _ids(self.params.get("course_id"))
        if not ids:
            raise RuleError("preferred_day requires course_id")
        self.course_ids = set(ids)
        self.days = {_norm_day(d) for d in (self.params.get("days") or [])}
        self.days.discard(None)

    def penalty(self, ctx, placement) -> float:
        total = 0.0
        for cid in self.course_ids:
            got = placement.get(cid)
            if got is not None and ctx.slot_day.get(got[1]) in self.days:
                total -= self.weight
        return total


class SpreadSessionsRule(Rule):
    """Soft: reward spreading a course's sessions across distinct days.

    The rule references a *list* of session ids that belong to one course.
    """

    def __post_init__(self) -> None:
        self.sessions = _ids(self.params.get("sessions"))

    def penalty(self, ctx, placement) -> float:
        days = [ctx.slot_day.get(placement[s][1]) for s in self.sessions if s in placement]
        if len(days) <= 1:
            return 0.0
        dupes = len(days) - len(set(days))
        return self.weight * dupes


_KINDS = {
    "forbid_slot": ForbidSlotRule,
    "fixed_slot": FixedSlotRule,
    "course_before": CourseBeforeRule,
    "same_day": SameDayRule,
    "no_same_day": NoSameDayRule,
    "preferred_day": PreferredDayRule,
    "spread_sessions": SpreadSessionsRule,
}


def rule_catalog() -> List[Dict[str, Any]]:
    """Machine-readable catalog of supported rule kinds (for the UI/docs)."""
    return [
        {"kind": "forbid_slot", "hard": True,
         "params": {"entity": "course|faculty|venue", "id": "int",
                    "slots": "[slot ids]", "days": "[Mon..Sun]"}},
        {"kind": "fixed_slot", "hard": True,
         "params": {"course_id": "int", "slot_id": "int", "venue_id": "int?"}},
        {"kind": "course_before", "hard": True,
         "params": {"course_a": "int", "course_b": "int"}},
        {"kind": "same_day", "hard": True, "params": {"courses": "[int, ...]"}},
        {"kind": "no_same_day", "hard": True,
         "params": {"course_a": "int", "course_b": "int"}},
        {"kind": "preferred_day", "hard": False,
         "params": {"course_id": "int", "days": "[Mon..Sun]"}},
        {"kind": "spread_sessions", "hard": False,
         "params": {"sessions": "[int, ...]"}},
    ]


def make_rule(row: Any) -> Optional[Rule]:
    """Build a Rule from a dict or a Constraint ORM row (None when unknown)."""
    if isinstance(row, dict):
        data = row
        kind = data.get("kind") or (data.get("constraint_data") or {}).get("kind")
        params = data.get("params") or (data.get("constraint_data") or {}).get("params") or {}
        hard = data.get("hard")
        weight = data.get("weight", 1.0)
        name = data.get("name", "")
    else:  # ORM object
        payload = getattr(row, "constraint_data", {}) or {}
        kind = payload.get("kind")
        params = payload.get("params", {})
        rtype = getattr(row, "type", "hard")
        hard = rtype != "soft"
        weight = getattr(row, "weight", 1.0)
        name = getattr(row, "name", "")
    if not kind or kind not in _KINDS:
        return None
    cls = _KINDS[kind]
    default_hard = cls is not PreferredDayRule and cls is not SpreadSessionsRule
    rule = cls(kind=kind, params=params, hard=default_hard if hard is None else bool(hard),
               weight=float(weight), name=name)
    return rule


def build_rules(rows: Optional[Iterable[Any]]) -> List[Rule]:
    """Build the active rule list, silently skipping unknown/malformed rows."""
    out: List[Rule] = []
    for row in rows or []:
        try:
            rule = make_rule(row)
        except (RuleError, TypeError, ValueError):
            rule = None
        if rule is not None:
            out.append(rule)
    return out
