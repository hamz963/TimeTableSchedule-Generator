"""Celery task queue: async path for timetable solving.

The synchronous POST /schedule/generate endpoint serves the <5 s real-time
requirement directly. This module provides the async alternative for very large
problems or batch workloads: enqueue with ``solve_timetable_task.delay(payload)``
and poll the result backend. Run a worker with:

    celery -A app.tasks.celery_app worker --loglevel=info
"""
from __future__ import annotations

from typing import Any, Dict

from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "timetable",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)


@celery_app.task(name="timetable.solve", bind=True, max_retries=0)
def solve_timetable_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Validate input, run the CP-SAT solver, return JSON-serializable result."""
    from app.services.solver import TimetableSolver
    from app.services.validator import ValidationError, validate_generate_request

    try:
        validate_generate_request(payload)
    except ValidationError as exc:
        return {"status": "invalid", "detail": str(exc), "assignments": []}

    result = TimetableSolver.generate(
        faculty=payload["faculty"],
        venues=payload["venues"],
        slots=payload["slots"],
        courses=payload["courses"],
        time_limit_seconds=float(payload.get("time_limit_seconds", 5.0)),
        locked_assignments=payload.get("locked_assignments") or None,
    )
    return {
        "status": result.status,
        "solver_time_ms": result.solver_time_ms,
        "assignments": result.assignments,
        "total_courses_scheduled": len(result.assignments),
        "conflicts_resolved": result.conflicts_resolved,
        "objective_value": result.objective_value,
    }


@celery_app.task(name="timetable.retrain", bind=True, max_retries=0)
def retrain_model_task(self) -> Dict[str, Any]:
    """Background job: retrain the preference model on all feedback."""
    from app.database import SessionLocal
    from app.ml.learner import train_model

    db = SessionLocal()
    try:
        return train_model(db)
    finally:
        db.close()
