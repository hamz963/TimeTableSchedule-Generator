"""User model: login identity + role."""
from sqlalchemy import Column, DateTime, Integer, String, func
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    # admin | scheduler | teacher
    role = Column(String(16), nullable=False, default="teacher", index=True)
    # Optional link: teacher-role users map to a teacher name in datasets.
    teacher_name = Column(String(200), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
