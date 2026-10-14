"""Timetable / schedule request-response schemas."""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class FacultyInput(BaseModel):
    id: int
    name: str = ""
    max_hours_per_day: int = 6
    max_days_per_week: int = 5
    preferences: List[int] = Field(default_factory=list)
    unavailable_slots: List[int] = Field(default_factory=list)


class VenueInput(BaseModel):
    id: int
    name: str = ""
    capacity: int = 30
    equipment: List[str] = Field(default_factory=list)
    available_slots: List[int] = Field(default_factory=list)


class SlotInput(BaseModel):
    id: int
    day_of_week: str = "Mon"
    start_time: str = "09:00"
    end_time: str = "10:00"
    duration_minutes: int = 60


class CourseInput(BaseModel):
    id: int
    name: str = ""
    code: str = ""
    faculty_id: int
    capacity_required: int = 20
    duration_minutes: int = 60
    required_equipment: List[str] = Field(default_factory=list)


class GenerateRequest(BaseModel):
    faculty: List[FacultyInput]
    venues: List[VenueInput]
    slots: List[SlotInput]
    courses: List[CourseInput]
    time_limit_seconds: float = Field(default=5.0, gt=0, le=60)
    # Optional pinned assignments to preserve: [{course_id, venue_id, slot_id}]
    locked_assignments: List[Dict[str, Any]] = Field(default_factory=list)


class Assignment(BaseModel):
    course_id: int
    faculty_id: int
    venue_id: int
    slot_id: int


class GenerateResponse(BaseModel):
    schedule_run_id: int
    status: str
    solver_time_ms: int
    assignments: List[Assignment]
    total_courses_scheduled: int
    conflicts_resolved: int = 0
    objective_value: Optional[float] = None
    summary: Dict[str, Any] = Field(default_factory=dict)


class RescheduleRequest(BaseModel):
    schedule_run_id: int
    faculty: List[FacultyInput]
    venues: List[VenueInput]
    slots: List[SlotInput]
    courses: List[CourseInput]
    # e.g. {"unavailable_venue_slots": [{"venue_id": 1, "slot_id": 2}], "cancelled": [course_id]}
    changes: Dict[str, Any] = Field(default_factory=dict)
    time_limit_seconds: float = Field(default=5.0, gt=0, le=60)


class AnalyticsResponse(BaseModel):
    schedule_run_id: int
    faculty_workload: Dict[int, Any]
    room_utilization: Dict[int, Any]
    preference_satisfaction_pct: float
    slots_filled_pct: float
    solver_time_ms: int
    solver_status: str
