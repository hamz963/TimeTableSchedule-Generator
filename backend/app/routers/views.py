"""Audience views router: same timetable, per-user perspectives."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models.user import User
from app.services.views import VIEWS, build_view

router = APIRouter(tags=["views"], dependencies=[Depends(get_current_user)])


@router.get("/schedule/{run_id}/views")
def get_view(run_id: int, view: str = "master", db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    if view not in VIEWS:
        raise HTTPException(status_code=400, detail=f"unknown view '{view}'; choose from {VIEWS}")
    if user.role == "teacher":
        if view != "teacher":
            raise HTTPException(
                status_code=403,
                detail="Teacher accounts can only view their own teacher schedule",
            )
        if not user.teacher_name:
            raise HTTPException(
                status_code=403,
                detail="No teacher is linked to this account; ask an admin to link one",
            )
    try:
        data = build_view(
            db, run_id, view,
            teacher_only=user.teacher_name if user.role == "teacher" else None,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Schedule run not found")
    return data
