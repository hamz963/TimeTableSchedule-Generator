"""Shared FastAPI dependencies."""
from app.config import Settings, get_settings
from app.database import get_db

__all__ = ["get_settings", "get_db", "Settings"]
