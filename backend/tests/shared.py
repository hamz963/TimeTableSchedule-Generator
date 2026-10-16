"""Shared SQLite-backed TestClient: one engine for the whole suite."""
import os

# The suite fires hundreds of requests from one test IP; disable throttling so
# it never trips. The dedicated security test re-enables it explicitly.
os.environ.setdefault("RATE_LIMIT_PER_MINUTE", "0")

from typing import Optional
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app as fastapi_app
import app.models as _models  # noqa: F401  (register tables)

engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base.metadata.create_all(bind=engine)

app = fastapi_app


def override_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_db

_admin_token: Optional[str] = None


def _seed_admin():
    """Seed admin/admin and mint a token so the suite exercises authed routes."""
    from app import auth as auth_svc
    from app.models.user import User

    db = TestingSession()
    try:
        admin = db.query(User).filter(User.username == "admin").first()
        if admin is None:
            admin = User(username="admin",
                         password_hash=auth_svc.hash_password("admin"),
                         role="admin")
            db.add(admin)
            db.commit()
            db.refresh(admin)
        return auth_svc.create_token(admin.id, admin.username, admin.role)
    finally:
        db.close()


def get_client() -> TestClient:
    global _admin_token
    if _admin_token is None:
        _admin_token = _seed_admin()
    return TestClient(app, headers={"Authorization": f"Bearer {_admin_token}"})


def get_session():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()
