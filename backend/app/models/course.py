"""Course model."""
from sqlalchemy import Column, ForeignKey, Integer, String, JSON
from app.database import Base


class Course(Base):
    __tablename__ = "course"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    code = Column(String(64), nullable=False, unique=True, index=True)
    faculty_id = Column(Integer, ForeignKey("faculty.id", ondelete="SET NULL"), nullable=True, index=True)
    capacity_required = Column(Integer, nullable=False, default=20)
    duration_minutes = Column(Integer, nullable=False, default=60)
    # Required equipment, e.g. ["projector"]
    required_equipment = Column(JSON, nullable=False, default=list)
