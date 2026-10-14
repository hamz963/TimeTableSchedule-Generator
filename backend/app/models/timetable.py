"""Generated timetable entries + schedule runs."""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, JSON, func
from app.database import Base


class ScheduleRun(Base):
    __tablename__ = "schedule_run"

    id = Column(Integer, primary_key=True, index=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    total_time_ms = Column(Integer, nullable=False, default=0)
    total_courses_scheduled = Column(Integer, nullable=False, default=0)
    conflicts_resolved = Column(Integer, nullable=False, default=0)
    solver_status = Column(String(32), nullable=False, default="unknown", index=True)
    # Display labels + planner summary (course/slot/teacher/room names, days,
    # breaks, fairness notes) so views/exports render without refetching input.
    summary_data = Column(JSON, nullable=False, default=dict)


class TimetableEntry(Base):
    __tablename__ = "timetable_entry"

    id = Column(Integer, primary_key=True, index=True)
    schedule_run_id = Column(Integer, ForeignKey("schedule_run.id", ondelete="CASCADE"), nullable=False, index=True)
    generated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    status = Column(String(32), nullable=False, default="completed", index=True)
    course_id = Column(Integer, ForeignKey("course.id", ondelete="CASCADE"), nullable=False, index=True)
    faculty_id = Column(Integer, ForeignKey("faculty.id", ondelete="SET NULL"), nullable=True, index=True)
    venue_id = Column(Integer, ForeignKey("venue.id", ondelete="SET NULL"), nullable=True, index=True)
    slot_id = Column(Integer, ForeignKey("time_slot.id", ondelete="SET NULL"), nullable=True, index=True)
    solver_time_ms = Column(Integer, nullable=False, default=0)
    conflict_count = Column(Integer, nullable=False, default=0)
