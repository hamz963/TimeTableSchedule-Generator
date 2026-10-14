"""Constraint schemas."""
from typing import Any, Dict, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class ConstraintCreate(BaseModel):
    type: Literal["hard", "soft"]
    name: str
    description: str = ""
    weight: float = Field(default=1.0, ge=0)
    constraint_data: Dict[str, Any] = Field(default_factory=dict)


class ConstraintRead(ConstraintCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int


class ConstraintUpdate(BaseModel):
    type: Optional[Literal["hard", "soft"]] = None
    name: Optional[str] = None
    description: Optional[str] = None
    weight: Optional[float] = Field(default=None, ge=0)
    constraint_data: Optional[Dict[str, Any]] = None
