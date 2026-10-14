"""Feedback + ML model registry models."""
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text, JSON, func
from app.database import Base


class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, index=True)
    schedule_run_id = Column(
        Integer, ForeignKey("schedule_run.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    teacher_name = Column(String(200), nullable=False, index=True)
    satisfaction_score = Column(Integer, nullable=False)  # 1-5
    preferred_time = Column(String(32), nullable=False, default="")  # Morning/Afternoon/Evening/""
    workload_satisfaction = Column(Integer, nullable=False, default=3)  # 1-5
    comments = Column(Text, nullable=False, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MLModel(Base):
    """Registry of trained preference models (one row per training run)."""

    __tablename__ = "ml_model"

    id = Column(Integer, primary_key=True, index=True)
    version = Column(Integer, nullable=False, unique=True, index=True)
    trained_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    training_samples = Column(Integer, nullable=False, default=0)
    accuracy = Column(Float, nullable=False, default=0.0)
    params = Column(JSON, nullable=False, default=dict)
