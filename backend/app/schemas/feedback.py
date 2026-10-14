"""Feedback schemas."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class FeedbackCreate(BaseModel):
    schedule_run_id: int
    teacher_name: str = Field(min_length=1)
    satisfaction_score: int = Field(ge=1, le=5)
    preferred_time: str = ""  # Morning | Afternoon | Evening | ""
    workload_satisfaction: int = Field(default=3, ge=1, le=5)
    comments: str = ""


class FeedbackRead(FeedbackCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: Optional[datetime] = None


class SuggestRequest(BaseModel):
    teacher_name: str = Field(min_length=1)
    total_minutes: int = Field(gt=0)
    period_minutes: int = Field(default=60, ge=15, le=240)
    slots: list = Field(default_factory=list)  # [{id, day_of_week, start_time}]
