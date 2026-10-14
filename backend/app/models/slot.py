"""Time slot model."""
from sqlalchemy import Column, Integer, String, Time
from app.database import Base


class TimeSlot(Base):
    __tablename__ = "time_slot"

    id = Column(Integer, primary_key=True, index=True)
    day_of_week = Column(String(16), nullable=False, index=True)  # Mon..Sun
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    duration_minutes = Column(Integer, nullable=False, default=60)
