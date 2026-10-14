"""FastAPI entry point."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import constraints, health, schedule, timetable, feedback, ml, views, export, chat, upload, teachers, auth

settings = get_settings()
log = logging.getLogger("timetable.startup")


def _run_migrations() -> None:
    """Bring the database to `head` on startup (fresh `docker compose up` just works).

    Falls back to create_all when Alembic can't run (e.g. minimal dev setup).
    Never raises: a DB-less boot still serves health/docs; DB endpoints fail
    loudly per-request instead.
    """
    try:
        from alembic import command
        from alembic.config import Config

        ini = Path(__file__).resolve().parent.parent / "alembic.ini"
        cfg = Config(str(ini))
        cfg.set_main_option("script_location", str(ini.parent / "alembic"))
        command.upgrade(cfg, "head")
        log.info("database migrated to head")
        return
    except Exception as exc:  # pragma: no cover - environment dependent
        log.warning("alembic upgrade failed (%s); falling back to create_all", exc)
    try:
        from app.database import init_db

        init_db()
    except Exception as exc:  # pragma: no cover - environment dependent
        log.warning("create_all failed (%s); running without a database", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if len(get_settings().jwt_secret) < 32:
        log.warning("JWT_SECRET is shorter than 32 chars; set a long random value in production.")
    _run_migrations()
    try:
        from app.auth import seed_admin
        from app.database import SessionLocal

        db = SessionLocal()
        try:
            seed_admin(db)
        finally:
            db.close()
    except Exception as exc:  # pragma: no cover - environment dependent
        log.warning("admin seeding failed (%s)", exc)
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Constraint-based university timetable optimization engine (OR-Tools CP-SAT).",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(schedule.router)
app.include_router(constraints.router)
app.include_router(timetable.router)
app.include_router(feedback.router)
app.include_router(ml.router)
app.include_router(views.router)
app.include_router(export.router)
app.include_router(chat.router)
app.include_router(upload.router)
app.include_router(teachers.router)
app.include_router(auth.router)


@app.get("/", tags=["root"])
def root():
    return {"service": settings.app_name, "version": settings.app_version, "docs": "/docs"}
