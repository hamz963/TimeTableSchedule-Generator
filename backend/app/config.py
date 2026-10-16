"""Application configuration via environment variables."""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Time Table Schedule Generator"
    app_version: str = "1.0.0"
    solver_version: str = "ortools-9.15-cpsat"
    environment: str = "development"
    debug: bool = False

    database_url: str = "postgresql+psycopg2://timetable:timetable@localhost:5432/timetable"
    # Redis backs shared chat state + the real-time event bus across replicas.
    # When unreachable, the app degrades to in-process state (single replica).
    redis_url: str = "redis://localhost:6379/0"
    chat_ttl_seconds: int = 3600  # chat conversation lifetime in Redis
    events_channel: str = "timetable:events"

    # Rate limiting (per client IP). 0 disables.
    rate_limit_per_minute: int = 120
    rate_limit_burst: int = 40
    # Require a valid JWT (as ?token=) on the SSE stream.
    events_require_auth: bool = False

    solver_time_limit_seconds: float = 5.0
    solver_num_workers: int = 8
    #: Wall-clock budget (seconds) the metaheuristic optimizer may spend on the
    #: large-instance path. Capped by the remaining request budget.
    solver_optimize_seconds: float = 1.5
    max_hours_per_day_default: int = 6

    cors_origins: str = "http://localhost:3000"
    gemini_api_key: str = ""  # optional: enables Gemini reply polishing
    ml_model_dir: str = ""  # optional: shared volume for model files (default: app/ml/models)
    jwt_secret: str = "dev-only-change-me"  # set JWT_SECRET in production
    admin_username: str = "admin"
    admin_password: str = "admin"  # change immediately after first boot


@lru_cache
def get_settings() -> Settings:
    return Settings()
