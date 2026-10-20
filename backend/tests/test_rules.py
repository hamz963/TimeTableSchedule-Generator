"""Declarative rules: registry, resolution, rebasing and end-to-end enforcement."""
import pytest

from app.engine.constraints import verify
from app.engine.context import build_context
from app.engine.heuristic import greedy_assign
from app.engine.rules import build_rules, make_rule, rule_catalog
from app.services.planner import build_problem, rebase_ids, resolve_rules
from app.services.solver import TimetableSolver
from app.services.validator import ValidationError


def _problem(**overrides):
    payload = {
        "teachers": [{"name": "Alice"}, {"name": "Bob"}],
        "courses": [
            {"name": "Math", "teacher": "Alice", "credit_hours": 1},
            {"name": "Art", "teacher": "Bob", "credit_hours": 1},
        ],
        "rooms": [],
        "days": ["Mon", "Tue", "Wed", "Thu", "Fri"],
        "day_start": "08:00", "day_end": "15:00", "period_minutes": 60,
        "gap_minutes": 10, "lunch_break": True, "lunch_start": "12:00", "lunch_end": "13:00",
    }
    payload.update(overrides)
    return payload


def test_rule_catalog_shape():
    kinds = {r["kind"] for r in rule_catalog()}
    assert {"course_before", "forbid_slot", "no_same_day", "preferred_day"} <= kinds


def test_make_rule_skips_unknown_kind():
    assert make_rule({"kind": "does_not_exist", "params": {}}) is None
    assert make_rule({"kind": "course_before", "params": {"course_a": 1, "course_b": 2}}) is not None


def test_forbid_slot_blocks_placement_locally():
    faculty, venues, slots, courses = build_problem(_problem())["faculty"], None, None, None
    p = build_problem(_problem(rules=[{
        "kind": "forbid_slot",
        "params": {"entity": "faculty", "id": "Bob", "days": ["Wed"]},
    }]))
    ctx = build_context(p["faculty"], p["venues"], p["slots"], p["courses"],
                        rules=build_rules(p["rules"]))
    bob_id = next(f["id"] for f in p["faculty"] if f["name"] == "Bob")
    wed_slot = next(s["id"] for s in p["slots"] if s["day_of_week"] == "Wed")
    art = next(c for c in p["courses"] if "Art" in c["name"])
    assert not ctx.placement_allowed(art["id"], p["venues"][0]["id"], wed_slot)


def test_course_before_enforced_end_to_end():
    p = build_problem(_problem(rules=[{
        "kind": "course_before", "params": {"course_a": "Math", "course_b": "Art"}}]))
    rules = build_rules(p["rules"])
    result = TimetableSolver.generate(
        p["faculty"], p["venues"], p["slots"], p["courses"],
        time_limit_seconds=5, session_groups=p["session_groups"], rules=rules,
    )
    assert result.status in ("optimal", "feasible")
    assert TimetableSolver.verify(result.assignments, p["courses"], p["faculty"],
                                  p["venues"], p["slots"], p["session_groups"]) == []
    slot_day = {s["id"]: (s["start_time"], s["day_of_week"]) for s in p["slots"]}
    by_course = {a["course_id"]: slot_day[a["slot_id"]] for a in result.assignments}
    math = next(v for k, v in by_course.items() if str(k) in p["summary"]["course_labels"]
                and p["summary"]["course_labels"][str(k)] == "Math")
    art = next(v for k, v in by_course.items() if p["summary"]["course_labels"].get(str(k)) == "Art")
    assert math < art


def test_course_before_combined_with_forbid_slot_stays_feasible():
    """Regression: greedy placed the dependent course first and gave up.

    ``course_before`` + ``forbid_slot`` used to be reported infeasible on a
    trivially satisfiable instance, because the constructive heuristic sorted
    purely by candidate count and could schedule ``Art`` before ``Math`` -- so
    the prerequisite could never precede it. The build order now follows the
    precedence ranking.
    """
    p = build_problem(_problem(
        courses=[
            {"name": "Math", "teacher": "Alice", "credit_hours": 3},
            {"name": "Art", "teacher": "Bob", "credit_hours": 1},
        ],
        rules=[
            {"kind": "course_before", "params": {"course_a": "Math", "course_b": "Art"}},
            {"kind": "forbid_slot",
             "params": {"entity": "faculty", "id": "Bob", "days": ["Fri"]}},
        ],
    ))
    rules = build_rules(p["rules"])
    result = TimetableSolver.generate(
        p["faculty"], p["venues"], p["slots"], p["courses"],
        time_limit_seconds=5, session_groups=p["session_groups"], rules=rules,
    )
    assert result.status in ("optimal", "feasible")
    assert len(result.assignments) == 4
    ctx = build_context(p["faculty"], p["venues"], p["slots"], p["courses"],
                        session_groups=p["session_groups"], rules=rules)
    assert verify(result.assignments, p["courses"], p["faculty"], p["venues"],
                  p["slots"], p["session_groups"], ctx=ctx) == []
    days = {s["id"]: s["day_of_week"] for s in p["slots"]}
    labels = p["summary"]["course_labels"]
    art_slots = [a["slot_id"] for a in result.assignments if labels[str(a["course_id"])] == "Art"]
    assert art_slots and all(days[sid] != "Fri" for sid in art_slots)


def test_no_same_day_enforced_end_to_end():
    p = build_problem(_problem(rules=[{
        "kind": "no_same_day", "params": {"course_a": "Math", "course_b": "Art"}}]))
    rules = build_rules(p["rules"])
    result = TimetableSolver.generate(
        p["faculty"], p["venues"], p["slots"], p["courses"],
        time_limit_seconds=5, session_groups=p["session_groups"], rules=rules,
    )
    slot_day = {s["id"]: s["day_of_week"] for s in p["slots"]}
    days = {p["summary"]["course_labels"][str(a["course_id"])]: slot_day[a["slot_id"]]
            for a in result.assignments}
    assert days["Math"] != days["Art"]


def test_resolve_rules_maps_names_and_rejects_unknown():
    p = build_problem(_problem())
    course_sessions = {}
    for cid, label in p["summary"]["course_labels"].items():
        course_sessions.setdefault(label.split(" (")[0], []).append(int(cid))
    teacher_ids = {f["name"]: f["id"] for f in p["faculty"]}
    resolved = resolve_rules(
        [{"kind": "course_before", "params": {"course_a": "Math", "course_b": "Art"}}],
        course_sessions, teacher_ids,
    )
    assert resolved[0]["params"]["course_a"] == course_sessions["Math"]
    with pytest.raises(ValidationError, match="unknown course"):
        resolve_rules([{"kind": "course_before", "params": {"course_a": "Ghost", "course_b": "Art"}}],
                      course_sessions, teacher_ids)


def test_rebase_rules_shifts_ids():
    p = build_problem(_problem(rules=[{
        "kind": "course_before", "params": {"course_a": "Math", "course_b": "Art"}}]))
    base_ids = {int(k) for k in p["summary"]["course_labels"]}
    rebased = rebase_ids(p, 100_000)
    for r in rebased["rules"]:
        assert all(v >= 100_000 for v in r["params"]["course_a"])
        assert all(v >= 100_000 for v in r["params"]["course_b"])
    assert base_ids  # sanity: original had ids


def test_relational_rules_reach_the_exact_solver():
    """course_before / same_day / no_same_day are encoded in CP-SAT, not just greedy.

    These three used to force the heuristic path on every instance, however
    small — the exact model only ever saw forbid_slot / fixed_slot.
    """
    cases = {
        "course_before": {"course_a": "Math", "course_b": "Art"},
        "same_day": {"courses": ["Math", "Art"]},
        "no_same_day": {"course_a": "Math", "course_b": "Art"},
    }
    for kind, params in cases.items():
        p = build_problem(_problem(rules=[{"kind": kind, "params": params}]))
        rules = build_rules(p["rules"])
        result = TimetableSolver.generate(
            p["faculty"], p["venues"], p["slots"], p["courses"],
            time_limit_seconds=5, session_groups=p["session_groups"], rules=rules,
        )
        assert result.engine["path"] == "exact", f"{kind} did not reach CP-SAT"
        ctx = build_context(p["faculty"], p["venues"], p["slots"], p["courses"],
                            session_groups=p["session_groups"], rules=rules)
        assert verify(result.assignments, p["courses"], p["faculty"], p["venues"],
                      p["slots"], p["session_groups"], ctx=ctx) == [], kind


def test_same_day_is_enforced_exactly():
    p = build_problem(_problem(rules=[
        {"kind": "same_day", "params": {"courses": ["Math", "Art"]}}]))
    rules = build_rules(p["rules"])
    result = TimetableSolver.generate(
        p["faculty"], p["venues"], p["slots"], p["courses"],
        time_limit_seconds=5, session_groups=p["session_groups"], rules=rules,
    )
    labels = p["summary"]["course_labels"]
    days = {s["id"]: s["day_of_week"] for s in p["slots"]}
    by_label = {labels[str(a["course_id"])]: days[a["slot_id"]] for a in result.assignments}
    assert by_label["Math"] == by_label["Art"]


def test_rule_compile_failure_falls_back_instead_of_silently_dropping(monkeypatch):
    """A rule that cannot be encoded must not be dropped without a trace.

    The exact path is chosen for this instance; forcing its compile to raise
    must send the solver down the verified heuristic path, never return an
    "optimal" timetable that breaks the rule.
    """
    from app.engine.rules import ForbidSlotRule

    def explode(self, ctx, model, x):
        raise RuntimeError("boom")

    monkeypatch.setattr(ForbidSlotRule, "cp_compile", explode)
    p = build_problem(_problem(rules=[{
        "kind": "forbid_slot",
        "params": {"entity": "faculty", "id": "Bob", "days": ["Fri"]},
    }]))
    rules = build_rules(p["rules"])
    result = TimetableSolver.generate(
        p["faculty"], p["venues"], p["slots"], p["courses"],
        time_limit_seconds=5, session_groups=p["session_groups"], rules=rules,
    )
    assert result.engine["path"] != "exact"
    ctx = build_context(p["faculty"], p["venues"], p["slots"], p["courses"],
                        session_groups=p["session_groups"], rules=rules)
    assert verify(result.assignments, p["courses"], p["faculty"], p["venues"],
                  p["slots"], p["session_groups"], ctx=ctx) == []


def test_preferred_day_is_soft_and_does_not_break_feasibility():
    p = build_problem(_problem(rules=[{
        "kind": "preferred_day", "params": {"course_id": "Math", "days": ["Mon"]}}]))
    rules = build_rules(p["rules"])
    assert rules and rules[0].hard is False
    result = TimetableSolver.generate(
        p["faculty"], p["venues"], p["slots"], p["courses"],
        time_limit_seconds=5, session_groups=p["session_groups"], rules=rules,
    )
    assert result.status in ("optimal", "feasible")
