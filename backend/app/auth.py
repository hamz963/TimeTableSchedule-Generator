"""Auth: stdlib PBKDF2 passwords, PyJWT tokens, role gating.

No passlib/bcrypt dependency on purpose (version hell on new Pythons):
hashlib.pbkdf2_hmac with a per-user salt and 200k iterations.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db

_ITERATIONS = 200_000
_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _ITERATIONS)
    return f"pbkdf2_sha256${_ITERATIONS}${salt}${digest.hex()}"


def check_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt, hexdigest = stored.split("$")
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), salt.encode(), int(iters)
        )
        return hmac.compare_digest(digest.hex(), hexdigest)
    except (ValueError, AttributeError):
        return False


def create_token(user_id: int, username: str, role: str,
                 expires_hours: int = 12) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=expires_hours)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def _unauthorized(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


def decode_token(token: str) -> dict:
    """Decode/verify a JWT without touching the DB (used by the SSE endpoint,
    which authenticates via a query param since EventSource can't send headers)."""
    return jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])


def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: Session = Depends(get_db),
):
    """Authenticated user row (any role). 401 without a valid Bearer token."""
    from app.models.user import User

    if creds is None or not creds.credentials:
        raise _unauthorized()
    try:
        payload = jwt.decode(
            creds.credentials, get_settings().jwt_secret, algorithms=["HS256"]
        )
        user = db.get(User, int(payload.get("sub", 0)))
    except Exception:
        raise _unauthorized("Invalid or expired token")
    if user is None:
        raise _unauthorized()
    return user


def require_role(*roles: str):
    """Dependency factory: 403 unless the user has one of the given roles."""
    def _check(user=Depends(get_current_user)):
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail=f"Requires role: {' or '.join(roles)}")
        return user
    return _check


# Convenience aliases used by routers.
require_scheduler = require_role("admin", "scheduler")
require_admin = require_role("admin")


def authenticate(db: Session, username: str, password: str):
    from app.models.user import User

    user = db.query(User).filter(User.username == username).first()
    if user is None or not check_password(password, user.password_hash):
        return None
    return user


def seed_admin(db: Session):
    """Create the initial admin account if no users exist. Returns True if created."""
    import logging

    from app.models.user import User

    if db.query(User).count() > 0:
        return False
    settings = get_settings()
    db.add(User(username=settings.admin_username,
                password_hash=hash_password(settings.admin_password),
                role="admin"))
    db.commit()
    logging.getLogger("timetable.startup").warning(
        "Seeded initial admin user '%s' — change the password immediately.",
        settings.admin_username,
    )
    return True
