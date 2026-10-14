"""Teacher router: rename teachers (master row + every run summary)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import require_scheduler
from app.schemas.teacher import TeacherRename, TeacherRenameResult
from app.services.teachers import (
    BadTeacherNameError,
    TeacherNotFoundError,
    rename_teacher,
)

router = APIRouter(prefix="/teachers", tags=["teachers"],
                   dependencies=[Depends(require_scheduler)])


@router.patch("/{faculty_id}", response_model=TeacherRenameResult)
def rename_teacher_endpoint(faculty_id: int, payload: TeacherRename, db: Session = Depends(get_db)):
    try:
        result = rename_teacher(db, faculty_id, payload.name)
    except TeacherNotFoundError:
        raise HTTPException(status_code=404, detail="Teacher not found")
    except BadTeacherNameError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return TeacherRenameResult(**result)
