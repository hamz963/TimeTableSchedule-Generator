"""Health check router."""
import time
from fastapi import APIRouter
from sqlalchemy import text

from app.config import get_settings
from app.database import engine

router = APIRouter(tags=["health"])
_started = time.time()


@router.get("/health")
def health():
    settings = get_settings()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as exc:  # keep endpoint alive even without DB
        db_status = f"unavailable: {exc.__class__.__name__}"
    try:
        import ortools  # noqa: F401
        from ortools.sat.python import cp_model  # noqa: F401

        solver_status = "ready"
    except Exception as exc:
        solver_status = f"unavailable: {exc.__class__.__name__}"
    try:
        import redis as redis_lib

        redis_lib.Redis.from_url(settings.redis_url,
                                 socket_connect_timeout=2).ping()
        redis_status = "connected"
    except Exception:
        redis_status = "unavailable (async queue disabled)"
    try:
        from app.ml.learner import MODEL_PATH, SCALER_PATH

        ml_status = ("trained" if MODEL_PATH.exists() and SCALER_PATH.exists()
                     else "no model (submit feedback, then retrain)")
    except Exception:
        ml_status = "unavailable"
    return {
        "status": "ok",
        "solver_version": settings.solver_version,
        "app_version": settings.app_version,
        "database": db_status,
        "components": {
            "api": "ok",
            "solver": solver_status,
            "database": db_status,
            "redis": redis_status,
            "ml_model": ml_status,
        },
        "uptime_seconds": round(time.time() - _started, 2),
    }
