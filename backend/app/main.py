"""FastAPI entry point."""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.middleware import RateLimitMiddleware

from app.config import get_settings
from app.routers import (
    constraints, health, schedule, timetable, feedback, ml, views, export, chat,
    upload, teachers, auth, quality, events,
)

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
    # Bind the SSE broker to this loop so sync endpoints can publish to live
    # subscribers via call_soon_threadsafe.
    event_task = None
    try:
        from app.services.events import broker

        broker.bind_loop(asyncio.get_running_loop())
        # Relay events published by other replicas (no-op without Redis).
        event_task = asyncio.create_task(broker.run_redis_subscriber())
    except Exception as exc:  # pragma: no cover
        log.warning("event broker startup failed (%s)", exc)
    yield
    if event_task is not None:
        event_task.cancel()
        try:
            await event_task
        except asyncio.CancelledError:
            pass  # expected: we just cancelled our own subscriber task
        except Exception as exc:  # pragma: no cover - shutdown best effort
            log.warning("event broker shutdown error (%s)", exc)


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
# Per-IP throttling (raw ASGI; SSE-safe). Disabled when RATE_LIMIT_PER_MINUTE=0.
app.add_middleware(RateLimitMiddleware)

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
app.include_router(quality.router)
app.include_router(events.router)


@app.get("/", tags=["root"])
def root():
    return {"service": settings.app_name, "version": settings.app_version, "docs": "/docs"}
