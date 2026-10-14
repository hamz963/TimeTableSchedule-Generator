"""Faculty model."""
from sqlalchemy import Column, Integer, String, JSON
from app.database import Base


class Faculty(Base):
    __tablename__ = "faculty"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, index=True)
    department = Column(String(200), nullable=False, default="", index=True)
    email = Column(String(255), nullable=True)
    max_hours_per_day = Column(Integer, nullable=False, default=6)
    max_days_per_week = Column(Integer, nullable=False, default=5)
    # List of preferred slot ids, e.g. [1, 2, 5]
    preferences = Column(JSON, nullable=False, default=list)
    # List of unavailable slot ids, e.g. [9, 10]
    unavailable_slots = Column(JSON, nullable=False, default=list)
