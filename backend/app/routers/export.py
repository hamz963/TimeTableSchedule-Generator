"""Multi-format export router: CSV, XLSX, PDF, PNG, JPG, JSON, HTML."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import io

from app.database import get_db
from app.auth import get_current_user
from app.models.user import User
from app.services.exporter import FORMATS, export_view
from app.services.views import VIEWS

router = APIRouter(tags=["export"], dependencies=[Depends(get_current_user)])


@router.get("/export/{run_id}")
def export_schedule(run_id: int, view: str = "master", format: str = "xlsx",
                    db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    if view not in VIEWS:
        raise HTTPException(status_code=400, detail=f"unknown view '{view}'; choose from {VIEWS}")
    if format.lower() not in FORMATS:
        raise HTTPException(status_code=400, detail=f"unsupported format '{format}'; choose from {FORMATS}")
    if user.role == "teacher":
        if view != "teacher":
            raise HTTPException(
                status_code=403,
                detail="Teacher accounts can only export their own teacher schedule",
            )
        if not user.teacher_name:
            raise HTTPException(
                status_code=403,
                detail="No teacher is linked to this account; ask an admin to link one",
            )
    try:
        content, media_type, filename = export_view(
            db, run_id, view, format,
            teacher_only=user.teacher_name if user.role == "teacher" else None,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Schedule run not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return StreamingResponse(
        io.BytesIO(content),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
