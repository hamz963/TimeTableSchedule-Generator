"""Declarative scheduling rules accepted by the generate endpoints.

Example::

    {"kind": "course_before", "params": {"course_a": "Math", "course_b": "Art"},
     "name": "Math before Art"}
    {"kind": "forbid_slot", "params": {"entity": "faculty", "id": "Alice",
     "days": ["Fri"]}, "name": "no Friday classes for Alice"}
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class RuleInput(BaseModel):
    kind: str = Field(description="Rule type, see GET /schedule/rules/catalog")
    params: Dict[str, Any] = Field(default_factory=dict)
    hard: Optional[bool] = Field(
        default=None, description="Override hard/soft (defaults per rule kind)"
    )
    weight: float = Field(default=1.0, ge=0)
    name: str = ""
