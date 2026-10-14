"""Chat router: conversational multi-view schedule generation."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models.timetable import ScheduleRun
from app.models.user import User
from app.schemas.chat import ChatGenerate, ChatMessage, ChatStart
from app.services import chat as chat_service
from app.services.views import VIEWS
from app.services.exporter import FORMATS

router = APIRouter(prefix="/chat", tags=["chat"], dependencies=[Depends(get_current_user)])


@router.post("/start")
def start(payload: ChatStart):
    if payload.schedule_run_id is not None:
        # validated lazily against DB in generate; keep start cheap
        pass
    return chat_service.start_conversation(payload.schedule_run_id)


@router.post("/{conversation_id}/message")
def message(conversation_id: str, payload: ChatMessage, db: Session = Depends(get_db),
            user: User = Depends(get_current_user)):
    try:
        return chat_service.send_message(conversation_id, payload.message, db,
                                         actor_role=user.role)
    except KeyError:
        raise HTTPException(status_code=404, detail="Conversation not found")


@router.post("/{conversation_id}/generate")
def generate(conversation_id: str, payload: ChatGenerate, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    try:
        convo = chat_service.get_conversation(conversation_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Conversation not found")
    run_id = convo.get("schedule_run_id")
    if run_id is None:
        raise HTTPException(
            status_code=400,
            detail="This chat has no timetable attached; restart with a schedule_run_id",
        )
    if db.get(ScheduleRun, run_id) is None:
        raise HTTPException(status_code=404, detail="Schedule run not found")

    views = payload.views or sorted(convo.get("views", set()))
    formats = payload.formats or sorted(convo.get("formats", set()))
    if user.role == "teacher":
        if not user.teacher_name:
            raise HTTPException(
                status_code=403,
                detail="No teacher is linked to this account; ask an admin to link one",
            )
        views = ["teacher"]  # teachers only ever receive their own schedule
    bad_views = [v for v in views if v not in VIEWS]
    bad_formats = [f for f in formats if f not in FORMATS]
    if bad_views:
        raise HTTPException(status_code=400, detail=f"unknown views {bad_views}; choose from {VIEWS}")
    if bad_formats:
        raise HTTPException(status_code=400, detail=f"unknown formats {bad_formats}; choose from {FORMATS}")
    if not views or not formats:
        raise HTTPException(
            status_code=400,
            detail="No views/formats selected yet; chat a little more first",
        )
    urls = {
        v: {f: f"/export/{run_id}?view={v}&format={f}" for f in formats}
        for v in views
    }
    return {
        "conversation_id": conversation_id,
        "schedule_run_id": run_id,
        "schedules_generated": len(views) * len(formats),
        "views": urls,
    }
