"""Teacher-friendly input schemas: names + credit hours + day window.

The teacher only provides what they know; the planner (`services/planner.py`)
expands this into the full solver-ready problem (slots with breaks, rooms,
per-session courses).
"""
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator
import re

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_TIME_BANDS = ("", "Morning", "Afternoon", "Evening")


def _check_hhmm(v: str, field_name: str) -> str:
    if not _TIME_RE.match(v or ""):
        raise ValueError(f"{field_name} must be HH:MM (24h), e.g. '08:00'")
    return v


class SimpleTeacher(BaseModel):
    name: str = Field(min_length=1)
    max_hours_per_day: int = Field(default=6, ge=1, le=12)
    unavailable_days: List[str] = Field(default_factory=list)


class SimpleCourse(BaseModel):
    name: str = Field(min_length=1)
    teacher: str = Field(min_length=1)
    credit_hours: int = Field(default=3, ge=1, le=4)
    student_group: str = ""
    preferred_time: str = ""  # Morning | Afternoon | Evening | ""
    capacity_required: int = Field(default=30, ge=1)
    required_equipment: List[str] = Field(default_factory=list)

    @field_validator("preferred_time")
    @classmethod
    def _validate_band(cls, v: str) -> str:
        v = (v or "").strip().capitalize()
        if v not in _TIME_BANDS:
            raise ValueError("preferred_time must be Morning, Afternoon, Evening, or blank")
        return v


class SimpleRoom(BaseModel):
    name: str = Field(min_length=1)
    capacity: int = Field(default=30, ge=1)


class SimpleGenerateRequest(BaseModel):
    teachers: List[SimpleTeacher] = Field(min_length=1)
    courses: List[SimpleCourse] = Field(min_length=1)
    rooms: List[SimpleRoom] = Field(default_factory=list)  # auto-created if empty
    days: List[str] = Field(default_factory=lambda: ["Mon", "Tue", "Wed", "Thu", "Fri"])
    day_start: str = "09:00"
    day_end: str = "17:00"
    period_minutes: int = Field(default=60, ge=15, le=240)
    gap_minutes: int = Field(default=30, ge=0, le=60)
    lunch_break: bool = True
    lunch_start: str = "12:00"
    lunch_end: str = "14:00"
    max_consecutive_periods: int = Field(
        default=2, ge=0, le=8,
        description="Max back-to-back periods per teacher per day (break after); 0 = off",
    )
    use_ml_preferences: bool = False  # fill slot preferences from learned model
    time_limit_seconds: float = Field(default=5.0, gt=0, le=60)

    @field_validator("day_start")
    @classmethod
    def _validate_start(cls, v: str) -> str:
        return _check_hhmm(v, "day_start")

    @field_validator("day_end")
    @classmethod
    def _validate_end(cls, v: str) -> str:
        return _check_hhmm(v, "day_end")

    @field_validator("lunch_start")
    @classmethod
    def _validate_lunch_start(cls, v: str) -> str:
        return _check_hhmm(v, "lunch_start")

    @field_validator("lunch_end")
    @classmethod
    def _validate_lunch_end(cls, v: str) -> str:
        return _check_hhmm(v, "lunch_end")
