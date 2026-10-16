"""Quality / benchmark schemas."""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.schemas.rule import RuleInput


class BenchmarkRequest(BaseModel):
    """Compare greedy-only vs. optimized on either a supplied or synthetic set."""

    faculty: Optional[List[Dict[str, Any]]] = None
    venues: Optional[List[Dict[str, Any]]] = None
    slots: Optional[List[Dict[str, Any]]] = None
    courses: Optional[List[Dict[str, Any]]] = None
    # When the above are omitted, a synthetic instance of this size is built.
    n_faculty: int = Field(default=50, ge=1, le=1000)
    n_rooms: int = Field(default=20, ge=1, le=500)
    n_courses: int = Field(default=100, ge=1, le=5000)
    n_slots: int = Field(default=40, ge=1, le=2000)
    optimize_seconds: float = Field(default=1.0, ge=0.05, le=30)
    seed: int = 12345
    rules: List[RuleInput] = Field(default_factory=list)


class QualityReport(BaseModel):
    schedule_run_id: int
    quality: Dict[str, Any] = Field(default_factory=dict)
    engine: Dict[str, Any] = Field(default_factory=dict)
