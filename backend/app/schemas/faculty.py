"""Faculty schemas."""
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class FacultyCreate(BaseModel):
    name: str
    department: str = ""
    email: Optional[str] = None
    max_hours_per_day: int = Field(default=6, ge=1, le=24)
    max_days_per_week: int = Field(default=5, ge=1, le=7)
    preferences: List[int] = Field(default_factory=list)
    unavailable_slots: List[int] = Field(default_factory=list)


class FacultyRead(FacultyCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
