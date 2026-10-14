"""Chat schemas."""
from typing import List, Optional
from pydantic import BaseModel, Field


class ChatStart(BaseModel):
    schedule_run_id: Optional[int] = None


class ChatMessage(BaseModel):
    message: str = Field(min_length=1)


class ChatGenerate(BaseModel):
    views: Optional[List[str]] = None  # defaults to conversation selection
    formats: Optional[List[str]] = None
