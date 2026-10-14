"""ML router: model stats, retraining, preference suggestions."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.auth import get_current_user, require_scheduler
from app.models.feedback import Feedback, MLModel
from app.schemas.feedback import SuggestRequest

router = APIRouter(prefix="/ml", tags=["ml"])


def _latest(db: Session):
    return db.query(MLModel).order_by(MLModel.version.desc()).first()


@router.get("/model-stats", dependencies=[Depends(get_current_user)])
def model_stats(db: Session = Depends(get_db)):
    latest = _latest(db)
    feedback_count = db.query(func.count(Feedback.id)).scalar() or 0
    return {
        "model_version": latest.version if latest else 0,
        "trained_on": latest.trained_at.isoformat() if latest else None,
        "training_samples": latest.training_samples if latest else 0,
        "model_accuracy": round(latest.accuracy, 4) if latest else 0.0,
        "evaluation": (latest.params or {}).get("evaluated_on") if latest else None,
        "feedback_count": feedback_count,
        "next_retrain": "on demand via POST /ml/retrain",
    }


@router.post("/retrain", dependencies=[Depends(require_scheduler)])
def retrain(db: Session = Depends(get_db)):
    """Retrain synchronously (small data); use the Celery task for background."""
    from app.ml.learner import train_model

    stats = train_model(db)
    if not stats.get("trained"):
        raise HTTPException(status_code=503, detail=stats.get("reason"))
    return {"status": "retrained", **stats}


@router.post("/retrain-async", dependencies=[Depends(require_scheduler)])
def retrain_async():
    """Enqueue background retraining on the Celery worker."""
    from app.tasks import retrain_model_task

    job = retrain_model_task.delay()
    return {"status": "retraining started in background", "task_id": job.id}


@router.post("/suggest", dependencies=[Depends(get_current_user)])
def suggest(payload: SuggestRequest, db: Session = Depends(get_db)):
    """ML-suggested time-of-day + preferred slot ids for a teacher's load."""
    from app.ml.predictor import suggest_preferences

    suggestion = suggest_preferences(
        db,
        teacher_name=payload.teacher_name,
        slots=payload.slots,
        total_minutes=payload.total_minutes,
        period_minutes=payload.period_minutes,
    )
    if suggestion is None:
        raise HTTPException(
            status_code=503,
            detail="No trained model yet; submit feedback and POST /ml/retrain first",
        )
    return {"teacher_name": payload.teacher_name, "suggestion": suggestion}
