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
    floating_count: int = Field(
        default=0,
        ge=0,
        description=(
            "Number of open commitments with no due time — today's list, "
            "written down without a clock time (ADR-0023)."
        ),
    )
    generated_at: datetime = Field(
        ...,
        description="Timestamp when this briefing was generated.",
    )
    cached: bool = Field(
        default=False,
        description="True if the briefing came from cache, False if freshly generated.",
    )
