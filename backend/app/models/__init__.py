"""SQLAlchemy models package."""
from app.models.faculty import Faculty
from app.models.venue import Venue
from app.models.slot import TimeSlot
from app.models.course import Course
from app.models.timetable import ScheduleRun, TimetableEntry
from app.models.constraint import Constraint
from app.models.feedback import Feedback, MLModel
from app.models.user import User

__all__ = [
    "Faculty",
    "Venue",
    "TimeSlot",
    "Course",
    "ScheduleRun",
    "TimetableEntry",
    "Constraint",
    "Feedback",
    "MLModel",
    "User",
]
