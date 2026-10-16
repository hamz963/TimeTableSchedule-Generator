"""Schedule generation + delta rescheduling router."""
from datetime import datetime, time as dtime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError as _IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import require_scheduler
from app.models.timetable import ScheduleRun, TimetableEntry
from app.schemas.edit import EditOperation, EditResponse
from app.schemas.simple import SimpleGenerateRequest
from app.schemas.timetable import GenerateRequest, GenerateResponse, RescheduleRequest
from app.services.planner import (
    ID_BLOCK,
    build_id_maps,
    build_problem,
    name_maps_from_summary,
    next_id_block,
    rebase_ids,
    rebase_rules,
    resolve_rules,
    summarize_advanced,
)
from app.engine.rules import build_rules, rule_catalog
from app.services.solver import TimetableSolver
from app.services.validator import (
    PayloadTooLargeError,
    ValidationError,
    validate_generate_request,
)

router = APIRouter(prefix="/schedule", tags=["schedule"],
                   dependencies=[Depends(require_scheduler)])


@router.get("/rules/catalog")
def rules_catalog():
    """Machine-readable catalog of supported declarative rule kinds."""
    return {"rules": rule_catalog()}


def _persisted_rules(db: Session) -> list:
    """Active constraint rows shaped as rule dicts (kind/params/hard/weight).

    This is what makes the Constraint CRUD drive the solver instead of being
    decorative. Rows without a ``constraint_data.kind`` are ignored.
    """
    from app.models.constraint import Constraint

    out = []
    for c in db.query(Constraint).all():
        data = c.constraint_data or {}
        kind = data.get("kind")
        if not kind:
            continue
        out.append({
            "kind": kind,
            "params": data.get("params") or {},
            "hard": c.type != "soft",
            "weight": c.weight,
            "name": c.name,
        })
    return out


def _parse_hhmm(value: str) -> dtime:
    try:
        h, m = str(value).split(":")
        return dtime(int(h), int(m))
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=400,
            detail=f"slot time '{value}' must be HH:MM (24h), e.g. '08:00'",
        )


def _persist_masters(
    db: Session,
    faculty: list,
    venues: list,
    slots: list,
    courses: list,
) -> None:
    """Upsert inline payload entities so timetable FKs hold (e.g. Postgres).

    The generate endpoints accept self-contained payloads without requiring
    master rows to pre-exist; merging them keeps every run self-contained
    and FK-safe.
    """
    from app.models.course import Course
    from app.models.faculty import Faculty
    from app.models.slot import TimeSlot
    from app.models.venue import Venue

    for f in faculty:
        db.merge(
            Faculty(
                id=f["id"],
                name=f.get("name", ""),
                department=f.get("department", ""),
                email=f.get("email"),
                max_hours_per_day=int(f.get("max_hours_per_day", 6)),
                max_days_per_week=int(f.get("max_days_per_week", 5)),
                preferences=f.get("preferences", []) or [],
                unavailable_slots=f.get("unavailable_slots", []) or [],
            )
        )
    db.flush()  # parents before children: Postgres checks FKs per statement
    for v in venues:
        db.merge(
            Venue(
                id=v["id"],
                name=v.get("name", ""),
                capacity=int(v.get("capacity", 30)),
                equipment=v.get("equipment", []) or [],
                available_slots=v.get("available_slots", []) or [],
            )
        )
    db.flush()
    for s in slots:
        db.merge(
            TimeSlot(
                id=s["id"],
                day_of_week=s.get("day_of_week", "Mon"),
                start_time=_parse_hhmm(s.get("start_time", "08:00")),
                end_time=_parse_hhmm(s.get("end_time", "09:00")),
                duration_minutes=int(s.get("duration_minutes", 60)),
            )
        )
    db.flush()
    for c in courses:
        code = c.get("code") or f"AUTO-{c['id']:04d}"
        # Codes are only unique per dataset, not globally: a different row
        # already holding this code means another dataset used the same label,
        # so namespace it instead of violating the unique constraint.
        clash = (
            db.query(Course.id)
            .filter(Course.code == code, Course.id != c["id"])
            .first()
        )
        if clash is not None:
            code = f"{code}#B{c['id'] // 100_000}"
        db.merge(
            Course(
                id=c["id"],
                name=c.get("name", ""),
                code=code,
                faculty_id=c.get("faculty_id"),
                capacity_required=int(c.get("capacity_required", 20)),
                duration_minutes=int(c.get("duration_minutes", 60)),
                required_equipment=c.get("required_equipment", []) or [],
            )
        )
    db.flush()


def _persist_result(db: Session, result, status_label: str, summary: Optional[dict] = None,
                    event_type: str = "schedule.created") -> int:
    run = ScheduleRun(
        completed_at=datetime.now(timezone.utc),
        total_time_ms=result.solver_time_ms,
        total_courses_scheduled=len(result.assignments),
        conflicts_resolved=result.conflicts_resolved,
        solver_status=result.status,
        summary_data=summary or {},
    )
    db.add(run)
    db.flush()  # assign run.id
    for a in result.assignments:
        db.add(
            TimetableEntry(
                schedule_run_id=run.id,
                status=status_label,
                course_id=a["course_id"],
                faculty_id=a.get("faculty_id"),
                venue_id=a.get("venue_id"),
                slot_id=a.get("slot_id"),
                solver_time_ms=result.solver_time_ms,
                conflict_count=0,
            )
        )
    db.commit()
    # Broadcast for live dashboards / notifications (best-effort, never fatal).
    try:
        from app.services.events import broker

        broker.publish({
            "type": event_type,
            "run_id": run.id,
            "status": result.status,
            "sessions": len(result.assignments),
            "quality_score": (result.metrics or {}).get("score", {}).get("score")
            if isinstance(result.metrics, dict) else None,
            "engine_path": (result.engine or {}).get("path"),
        })
    except Exception:  # pragma: no cover - events must never break a request
        pass
    return run.id


@router.post("/generate", response_model=GenerateResponse)
def generate_schedule(payload: GenerateRequest, db: Session = Depends(get_db)):
    try:
        validate_generate_request(payload.model_dump())
    except PayloadTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc))
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Retry on id-block races (see generate-simple).
    for _ in range(3):
        faculty = [f.model_dump() for f in payload.faculty]
        venues = [v.model_dump() for v in payload.venues]
        slots = [s.model_dump() for s in payload.slots]
        courses = [c.model_dump() for c in payload.courses]

        # Server-owned id space (same scheme as generate-simple): shift this
        # dataset into a fresh id block so its master rows can never collide
        # with other datasets' runs. NOTE: ids in the response are rebased.
        fid_map, vid_map, sid_map, cid_map = build_id_maps(
            faculty, venues, slots, courses, next_id_block(db)
        )
        for f in faculty:
            f["id"] = fid_map[f["id"]]
            f["unavailable_slots"] = [sid_map[s] for s in f.get("unavailable_slots", [])]
        for v in venues:
            v["id"] = vid_map[v["id"]]
            v["available_slots"] = [sid_map[s] for s in (v.get("available_slots") or [])]
        for s in slots:
            s["id"] = sid_map[s["id"]]
        for c in courses:
            c["id"] = cid_map[c["id"]]
            c["faculty_id"] = fid_map[c["faculty_id"]]
        locked = []
        for l in payload.locked_assignments or []:
            if (l.get("course_id") not in cid_map or l.get("venue_id") not in vid_map
                    or l.get("slot_id") not in sid_map):
                raise HTTPException(
                    status_code=400,
                    detail=f"locked assignment {l} references unknown course/room/slot",
                )
            locked.append({"course_id": cid_map[l["course_id"]],
                           "venue_id": vid_map[l["venue_id"]],
                           "slot_id": sid_map[l["slot_id"]]})

        raw_rules = [r.model_dump() for r in payload.rules]
        # Merge persisted constraint rows (global) with inline rules; persisted
        # rows that reference entities absent from this dataset are skipped.
        course_map = {c.get("name", ""): [c["id"]] for c in courses if c.get("name")}
        teacher_map = {f.get("name", ""): f["id"] for f in faculty if f.get("name")}
        raw_rules += resolve_rules(_persisted_rules(db), course_map, teacher_map, strict=False)
        rules = build_rules(rebase_rules(raw_rules, fid_map, vid_map, sid_map, cid_map))

        result = TimetableSolver.generate(
            faculty=faculty,
            venues=venues,
            slots=slots,
            courses=courses,
            time_limit_seconds=payload.time_limit_seconds,
            locked_assignments=locked or None,
            rules=rules or None,
        )
        if result.status in ("infeasible", "timeout") and not result.assignments:
            raise HTTPException(
                status_code=422,
                detail=f"Solver could not find a feasible timetable (status={result.status}). "
                "Relax constraints (availability, capacity, workload) and retry.",
            )
        try:
            _persist_masters(db, faculty, venues, slots, courses)
            summary = summarize_advanced(faculty, venues, slots, courses)
            summary["quality"] = result.metrics
            summary["engine"] = result.engine
            run_id = _persist_result(db, result, "completed", summary)
        except _IntegrityError:
            db.rollback()
            continue
        break
    else:
        raise HTTPException(
            status_code=503,
            detail="Concurrent id allocation conflict; please retry the request.",
        )
    return GenerateResponse(
        schedule_run_id=run_id,
        status=result.status,
        solver_time_ms=result.solver_time_ms,
        assignments=result.assignments,
        total_courses_scheduled=len(result.assignments),
        conflicts_resolved=result.conflicts_resolved,
        objective_value=result.objective_value,
        summary=summary,
        quality=result.metrics,
        engine=result.engine,
    )


@router.post("/generate-simple", response_model=GenerateResponse)
def generate_simple(payload: SimpleGenerateRequest, db: Session = Depends(get_db)):
    """Teacher-friendly generation: names + credit hours + day window in,
    fair conflict-free timetable out (slots with breaks auto-built)."""
    import copy as _copy

    try:
        pristine = build_problem(payload.model_dump())
    except PayloadTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc))
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Retry on id-block races: two concurrent requests can compute the same
    # fresh block; the loser re-resolves against the new maximum.
    for _ in range(3):
        problem = _copy.deepcopy(pristine)
        # Server-owned id space: shift the dataset into a fresh id block so its
        # master rows can never collide with other datasets' runs.
        problem = rebase_ids(problem, next_id_block(db))

        faculty, venues = problem["faculty"], problem["venues"]
        slots, courses = problem["slots"], problem["courses"]
        try:
            validate_generate_request(
                {"faculty": faculty, "venues": venues, "slots": slots, "courses": courses}
            )
        except PayloadTooLargeError as exc:
            raise HTTPException(status_code=413, detail=str(exc))
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        if payload.use_ml_preferences:
            _apply_ml_preferences(db, problem)

        # Persisted constraint rows are global: resolve them against this
        # dataset's ids and append (non-strict — unresolvable ones are skipped).
        course_map, teacher_map = name_maps_from_summary(problem["summary"])
        extra = resolve_rules(_persisted_rules(db), course_map, teacher_map, strict=False)
        rules = build_rules(list(problem.get("rules") or []) + extra)
        result = TimetableSolver.generate(
            faculty=faculty,
            venues=venues,
            slots=slots,
            courses=courses,
            time_limit_seconds=payload.time_limit_seconds,
            session_groups=problem["session_groups"],
            max_consecutive=int(payload.max_consecutive_periods),
            rules=rules or None,
        )
        if result.status in ("infeasible", "timeout") and not result.assignments:
            raise HTTPException(
                status_code=422,
                detail=f"Solver could not find a feasible timetable (status={result.status}). "
                "Try adding rooms, extending day_start/day_end, or lowering credit hours.",
            )
        problem["summary"]["quality"] = result.metrics
        problem["summary"]["engine"] = result.engine
        try:
            _persist_masters(db, faculty, venues, slots, courses)
            run_id = _persist_result(db, result, "completed", problem["summary"])
        except _IntegrityError:
            db.rollback()
            continue
        break
    else:
        raise HTTPException(
            status_code=503,
            detail="Concurrent id allocation conflict; please retry the request.",
        )
    return GenerateResponse(
        schedule_run_id=run_id,
        status=result.status,
        solver_time_ms=result.solver_time_ms,
        assignments=result.assignments,
        total_courses_scheduled=len(result.assignments),
        conflicts_resolved=result.conflicts_resolved,
        objective_value=result.objective_value,
        summary=problem["summary"],
        quality=result.metrics,
        engine=result.engine,
    )


def _apply_ml_preferences(db: Session, problem: dict) -> None:
    """Fill faculty slot preferences from the learned model (if available).

    Records per-teacher decisions in problem['summary']['ml_applied'].
    """
    from app.ml.predictor import suggest_preferences

    minutes_by_faculty: dict = {}
    for c in problem["courses"]:
        minutes_by_faculty[c["faculty_id"]] = (
            minutes_by_faculty.get(c["faculty_id"], 0)
            + int(c.get("duration_minutes", 60))
        )
    applied = {}
    for f in problem["faculty"]:
        try:
            suggestion = suggest_preferences(
                db,
                teacher_name=f.get("name", ""),
                slots=problem["slots"],
                total_minutes=minutes_by_faculty.get(f["id"], 60),
                period_minutes=60,
            )
        except Exception:
            suggestion = None
        if suggestion and suggestion.get("slot_ids"):
            f["preferences"] = suggestion["slot_ids"]
            applied[f.get("name", "")] = {
                "time_of_day": suggestion.get("time_of_day"),
                "confidence": suggestion.get("confidence"),
            }
    problem["summary"]["ml_applied"] = applied


@router.post("/reschedule", response_model=GenerateResponse)
def reschedule(payload: RescheduleRequest, db: Session = Depends(get_db)):
    """Delta-reschedule: re-solve while penalizing deviation from previous run."""
    previous_entries = (
        db.query(TimetableEntry)
        .filter(TimetableEntry.schedule_run_id == payload.schedule_run_id)
        .all()
    )
    if not previous_entries:
        raise HTTPException(status_code=404, detail="Previous schedule run not found")
    previous = [
        {"course_id": e.course_id, "venue_id": e.venue_id, "slot_id": e.slot_id}
        for e in previous_entries
    ]

    changes = payload.changes or {}
    blocked_vs = {(b.get("venue_id"), b.get("slot_id")) for b in changes.get("unavailable_venue_slots", [])}
    cancelled = set(changes.get("cancelled", []) or [])

    faculty = [f.model_dump() for f in payload.faculty]
    venues = [v.model_dump() for v in payload.venues]
    slots = [s.model_dump() for s in payload.slots]
    courses = [c.model_dump() for c in payload.courses if c.id not in cancelled]
    if not courses:
        raise HTTPException(status_code=400, detail="All courses cancelled; nothing to reschedule")

    # Apply blocked venue-slots by pruning venue availability dynamically.
    if blocked_vs:
        vid_to_blocked = {}
        for vid, sid in blocked_vs:
            vid_to_blocked.setdefault(vid, set()).add(sid)
        for v in venues:
            if v["id"] in vid_to_blocked and v.get("available_slots"):
                v["available_slots"] = [s for s in v["available_slots"] if s not in vid_to_blocked[v["id"]]]
            elif v["id"] in vid_to_blocked and not v.get("available_slots"):
                # Venue was available everywhere: restrict to all slots minus blocked.
                all_sids = [s["id"] for s in slots]
                v["available_slots"] = [s for s in all_sids if s not in vid_to_blocked[v["id"]]]

    try:
        validate_generate_request(
            {"faculty": faculty, "venues": venues, "slots": slots, "courses": courses}
        )
    except PayloadTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc))
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Rebase into the previous run's id block so `previous` (DB-space ids)
    # lines up with the rebuilt model. Legacy runs (small ids) map to
    # block 0 = identity.
    base = (min(e.course_id for e in previous_entries) // ID_BLOCK) * ID_BLOCK
    fid_map, vid_map, sid_map, cid_map = build_id_maps(
        faculty, venues, slots, courses, base
    )
    for f in faculty:
        f["id"] = fid_map[f["id"]]
        f["unavailable_slots"] = [sid_map[s] for s in f.get("unavailable_slots", [])]
    for v in venues:
        v["id"] = vid_map[v["id"]]
        v["available_slots"] = [sid_map[s] for s in (v.get("available_slots") or [])]
    for s in slots:
        s["id"] = sid_map[s["id"]]
    for c in courses:
        c["id"] = cid_map[c["id"]]
        c["faculty_id"] = fid_map[c["faculty_id"]]

    rules = build_rules(rebase_rules([r.model_dump() for r in payload.rules],
                                     fid_map, vid_map, sid_map, cid_map))
    result = TimetableSolver.generate(
        faculty=faculty, venues=venues, slots=slots, courses=courses,
        time_limit_seconds=payload.time_limit_seconds, previous=previous,
        rules=rules or None,
    )
    if result.status in ("infeasible", "timeout") and not result.assignments:
        raise HTTPException(status_code=422, detail=f"Reschedule infeasible (status={result.status})")
    _persist_masters(db, faculty, venues, slots, courses)
    summary = summarize_advanced(faculty, venues, slots, courses)
    summary["quality"] = result.metrics
    summary["engine"] = result.engine
    run_id = _persist_result(db, result, "completed", summary, event_type="schedule.rescheduled")
    return GenerateResponse(
        schedule_run_id=run_id,
        status=result.status,
        solver_time_ms=result.solver_time_ms,
        assignments=result.assignments,
        total_courses_scheduled=len(result.assignments),
        conflicts_resolved=result.conflicts_resolved,
        objective_value=result.objective_value,
        summary=summary,
        quality=result.metrics,
        engine=result.engine,
    )


@router.post("/{run_id}/edit", response_model=EditResponse)
def edit_schedule(run_id: int, payload: EditOperation, db: Session = Depends(get_db)):
    """Interactive edit: move / cancel / swap one session.

    Validated against all hard constraints; persisted as a NEW run so the
    original timetable is preserved. Used by the edit-tools UI and chatbot.
    """
    from app.services.edits import EditError, apply_edit, describe

    if db.get(ScheduleRun, run_id) is None:
        raise HTTPException(status_code=404, detail="Schedule run not found")
    try:
        result = apply_edit(db, run_id, payload.model_dump(exclude_unset=True))
    except EditError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    summary = (db.get(ScheduleRun, result["new_run_id"]).summary_data or {})
    return EditResponse(
        schedule_run_id=run_id,
        new_run_id=result["new_run_id"],
        assignments=result["assignments"],
        total_courses_scheduled=result["total_courses_scheduled"],
        description=describe(payload.model_dump(exclude_unset=True), summary),
    )
