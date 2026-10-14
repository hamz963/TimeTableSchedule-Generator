"""Feedback collection router: the data fuel for preference learning."""
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user
from app.models.feedback import Feedback
from app.models.timetable import ScheduleRun
from app.schemas.feedback import FeedbackCreate, FeedbackRead

router = APIRouter(tags=["feedback"], dependencies=[Depends(get_current_user)])


@router.post("/feedback", response_model=FeedbackRead, status_code=201)
def submit_feedback(payload: FeedbackCreate, db: Session = Depends(get_db)):
    if db.get(ScheduleRun, payload.schedule_run_id) is None:
        raise HTTPException(status_code=404, detail="Schedule run not found")
    if payload.preferred_time and payload.preferred_time not in (
        "Morning", "Afternoon", "Evening",
    ):
        raise HTTPException(
            status_code=400,
            detail="preferred_time must be Morning, Afternoon, Evening, or empty",
        )
    fb = Feedback(**payload.model_dump())
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return fb


@router.get("/feedback/schedule/{run_id}", response_model=List[FeedbackRead])
def list_feedback(run_id: int, db: Session = Depends(get_db)):
    return (
        db.query(Feedback)
        .filter(Feedback.schedule_run_id == run_id)
        .order_by(Feedback.id)
        .all()
    )
