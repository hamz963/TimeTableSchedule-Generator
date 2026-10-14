"""Time slot schemas."""
from datetime import time
from pydantic import BaseModel, ConfigDict, Field


class SlotCreate(BaseModel):
    day_of_week: str
    start_time: time
    end_time: time
    duration_minutes: int = Field(default=60, ge=15)


class SlotRead(SlotCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
