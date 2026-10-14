"""Auth router: login, profile, admin-only registration."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import auth as auth_svc
from app.database import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse, UserCreate, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])

VALID_ROLES = ("admin", "scheduler", "teacher")


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = auth_svc.authenticate(db, payload.username, payload.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return TokenResponse(
        access_token=auth_svc.create_token(user.id, user.username, user.role),
        username=user.username,
        role=user.role,
    )


@router.get("/me", response_model=UserRead)
def me(user: User = Depends(auth_svc.get_current_user)):
    return user


@router.post("/register", response_model=UserRead, status_code=201)
def register(payload: UserCreate, db: Session = Depends(get_db),
             admin: User = Depends(auth_svc.require_admin)):
    if payload.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"role must be one of {VALID_ROLES}")
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=400, detail="Username already taken")
    user = User(username=payload.username,
                password_hash=auth_svc.hash_password(payload.password),
                role=payload.role, teacher_name=payload.teacher_name)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
