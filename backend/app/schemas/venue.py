"""Venue schemas."""
from typing import List
from pydantic import BaseModel, ConfigDict, Field


class VenueCreate(BaseModel):
    name: str
    capacity: int = Field(default=30, ge=1)
    equipment: List[str] = Field(default_factory=list)
    available_slots: List[int] = Field(default_factory=list)


class VenueRead(VenueCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
