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
    # Sync URL used by SQLAlchemy; async not required for this service.
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/0"

    solver_time_limit_seconds: float = 5.0
    solver_num_workers: int = 8
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
