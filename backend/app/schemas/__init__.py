"""Pydantic schemas package."""
from app.schemas.faculty import FacultyCreate, FacultyRead
from app.schemas.venue import VenueCreate, VenueRead
from app.schemas.slot import SlotCreate, SlotRead
from app.schemas.constraint import ConstraintCreate, ConstraintRead
from app.schemas.simple import (
    SimpleCourse,
    SimpleGenerateRequest,
    SimpleRoom,
    SimpleTeacher,
)
from app.schemas.feedback import FeedbackCreate, FeedbackRead, SuggestRequest
from app.schemas.chat import ChatGenerate, ChatMessage, ChatStart
from app.schemas.edit import EditOperation, EditResponse
from app.schemas.teacher import TeacherRename, TeacherRenameResult
from app.schemas.timetable import (
    CourseInput,
    FacultyInput,
    GenerateRequest,
    Assignment,
    GenerateResponse,
    RescheduleRequest,
    AnalyticsResponse,
    VenueInput,
    SlotInput,
)

__all__ = [
    "FacultyCreate", "FacultyRead", "VenueCreate", "VenueRead",
    "SlotCreate", "SlotRead", "ConstraintCreate", "ConstraintRead",
    "CourseInput", "FacultyInput", "VenueInput", "SlotInput",
    "GenerateRequest", "Assignment", "GenerateResponse",
    "RescheduleRequest", "AnalyticsResponse",
    "SimpleTeacher", "SimpleCourse", "SimpleRoom", "SimpleGenerateRequest",
    "FeedbackCreate", "FeedbackRead", "SuggestRequest",
    "ChatStart", "ChatMessage", "ChatGenerate",
    "EditOperation", "EditResponse",
    "TeacherRename", "TeacherRenameResult",
]
