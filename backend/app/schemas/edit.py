"""Schedule-edit schemas (move / cancel / swap a session)."""
from typing import Optional
from pydantic import BaseModel, Field


class EditOperation(BaseModel):
    op: str = Field(description="move, cancel, or swap")
    course_id: Optional[int] = None
    to_slot_id: Optional[int] = None
    to_venue_id: Optional[int] = None
    course_id_a: Optional[int] = None
    course_id_b: Optional[int] = None


class EditResponse(BaseModel):
    schedule_run_id: int
    new_run_id: int
    status: str = "edited"
    assignments: list
    total_courses_scheduled: int
    description: str
