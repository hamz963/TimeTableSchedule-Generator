"""Venue / room model."""
from sqlalchemy import Column, Integer, String, JSON
from app.database import Base


class Venue(Base):
    __tablename__ = "venue"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, index=True)
    capacity = Column(Integer, nullable=False, default=30)
    # Equipment list, e.g. ["projector", "lab"]
    equipment = Column(JSON, nullable=False, default=list)
    # List of available slot ids; empty/None means all slots available
    available_slots = Column(JSON, nullable=False, default=list)
