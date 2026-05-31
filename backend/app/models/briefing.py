"""
briefing.py — Pydantic schemas for morning briefings.

Briefings are *ephemeral* in slice 4 — generated on demand from the
user's current commitment state, not persisted. Future slices may add
a `briefings` table for caching + history.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class BriefingResponse(BaseModel):
    """A morning briefing returned by GET /briefings/today."""

    content: str = Field(
        ...,
        description="The natural-language briefing text (LLM-generated).",
    )
    today_count: int = Field(
        ...,
        ge=0,
        description="Number of open commitments due today.",
    )
    overdue_count: int = Field(
        ...,
        ge=0,
        description="Number of open commitments past their due date.",
    )
    generated_at: datetime = Field(
        ...,
        description="Timestamp when this briefing was generated.",
    )
