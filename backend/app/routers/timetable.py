"""Timetable retrieval + analytics router."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models.timetable import ScheduleRun, TimetableEntry
from app.models.user import User
from app.schemas.timetable import AnalyticsResponse
from app.services import analytics as analytics_svc

router = APIRouter(tags=["timetable"], dependencies=[Depends(get_current_user)])


def _forbid_teacher_detail(user: User) -> None:
    if user.role == "teacher":
        raise HTTPException(
            status_code=403,
            detail="Teacher accounts use the teacher view (/schedule/{id}/views?view=teacher)",
        )


@router.get("/schedule/runs")
def list_runs(db: Session = Depends(get_db)):
    """Newest-first run index (powers pickers instead of hand-typed ids)."""
    runs = db.query(ScheduleRun).order_by(ScheduleRun.id.desc()).limit(200).all()
    return [
        {
            "schedule_run_id": r.id,
            "solver_status": r.solver_status,
            "total_time_ms": r.total_time_ms,
            "total_courses_scheduled": r.total_courses_scheduled,
            "started_at": r.started_at.isoformat() if r.started_at else None,
        }
        for r in runs
    ]


@router.get("/schedule/{run_id}")
def get_schedule(run_id: int, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    _forbid_teacher_detail(user)
    from app.models.course import Course
    from app.models.faculty import Faculty
    from app.models.slot import TimeSlot
    from app.models.venue import Venue

    run = db.get(ScheduleRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Schedule run not found")
    entries = (
        db.query(TimetableEntry).filter(TimetableEntry.schedule_run_id == run_id).all()
    )
    summary = run.summary_data or {}

    def slot_label(s) -> str:
        start = s.start_time.strftime("%H:%M") if hasattr(s.start_time, "strftime") else s.start_time
        end = s.end_time.strftime("%H:%M") if hasattr(s.end_time, "strftime") else s.end_time
        return f"{s.day_of_week} {start}–{end}"

    masters = summary.get("masters")
    if masters:
        # Dataset-scoped pickers (global tables accumulate many datasets).
        slot_rows = [
            {"id": s["id"], "day": s.get("day_of_week", "?"),
             "label": (summary.get("slot_labels") or {}).get(
                 str(s["id"]),
                 s.get("label") or f"{s.get('day_of_week', '?')} {s.get('start_time', '')}–{s.get('end_time', '')}")}
            for s in masters.get("slots", [])
        ]
        room_rows = [
            {"id": v["id"],
             "name": (summary.get("room_names") or {}).get(str(v["id"]), v.get("name", ""))}
            for v in masters.get("venues", [])
        ]
        course_rows = [
            {"id": c["id"],
             "name": (summary.get("course_labels") or {}).get(str(c["id"]), c.get("name", ""))}
            for c in masters.get("courses", [])
        ]
        teacher_rows = [
            {"id": f["id"],
             "name": (summary.get("teacher_names") or {}).get(str(f["id"]), f.get("name", ""))}
            for f in masters.get("faculty", [])
        ]
    else:
        slot_rows = [
            {"id": s.id, "day": s.day_of_week,
             "label": (summary.get("slot_labels") or {}).get(str(s.id), slot_label(s))}
            for s in db.query(TimeSlot).order_by(TimeSlot.id).all()
        ]
        room_rows = [
            {"id": v.id,
             "name": (summary.get("room_names") or {}).get(str(v.id), v.name)}
            for v in db.query(Venue).order_by(Venue.id).all()
        ]
        course_rows = [
            {"id": c.id,
             "name": (summary.get("course_labels") or {}).get(str(c.id), c.name)}
            for c in db.query(Course).order_by(Course.id).all()
        ]
        teacher_rows = [
            {"id": f.id,
             "name": (summary.get("teacher_names") or {}).get(str(f.id), f.name)}
            for f in db.query(Faculty).order_by(Faculty.id).all()
        ]

    return {
        "schedule_run_id": run.id,
        "solver_status": run.solver_status,
        "total_time_ms": run.total_time_ms,
        "total_courses_scheduled": run.total_courses_scheduled,
        "summary": summary,
        "assignments": [
            {
                "course_id": e.course_id,
                "faculty_id": e.faculty_id,
                "venue_id": e.venue_id,
                "slot_id": e.slot_id,
            }
            for e in entries
        ],
        # Full pickers for the edit-tools UI (server validates every edit).
        "slots": slot_rows,
        "rooms": room_rows,
        "courses": course_rows,
        "teachers": teacher_rows,
    }


@router.get("/analytics/schedule/{run_id}", response_model=AnalyticsResponse)
def get_analytics(run_id: int, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    _forbid_teacher_detail(user)
    run = db.get(ScheduleRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Schedule run not found")
    entries = (
        db.query(TimetableEntry).filter(TimetableEntry.schedule_run_id == run_id).all()
    )
    assignments = [
        {"course_id": e.course_id, "faculty_id": e.faculty_id,
         "venue_id": e.venue_id, "slot_id": e.slot_id}
        for e in entries
    ]
    # Real context from the run's own master snapshot (falls back to empty
    # for legacy runs without one, preserving old behavior there).
    masters = (run.summary_data or {}).get("masters") or {}
    computed = analytics_svc.compute_analytics(
        assignments,
        faculty=masters.get("faculty", []),
        venues=masters.get("venues", []),
        slots=masters.get("slots", []),
        solver_time_ms=run.total_time_ms, solver_status=run.solver_status,
    )
    return AnalyticsResponse(
        schedule_run_id=run_id,
        faculty_workload=computed["faculty_workload"],
        room_utilization=computed["room_utilization"],
        preference_satisfaction_pct=computed["preference_satisfaction_pct"],
        slots_filled_pct=computed["slots_filled_pct"],
        solver_time_ms=computed["solver_time_ms"],
        solver_status=computed["solver_status"],
    )
