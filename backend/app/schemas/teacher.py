"""Teacher rename schemas."""
from pydantic import BaseModel, Field


class TeacherRename(BaseModel):
    name: str = Field(min_length=1, description="New teacher name")


class TeacherRenameResult(BaseModel):
    id: int
    name: str
    runs_updated: int
    feedback_updated: int = 0
