"""
reflection.py — Pydantic schema for evening reflections.

Mirrors BriefingResponse's shape (see app/models/briefing.py), plus
abandoned_count — the reflection looks BACK on the whole day (done, still
open, and abandoned), where the morning briefing only looks forward.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class ReflectionResponse(BaseModel):
    """An evening reflection returned by GET /reflections/today."""

    content: str = Field(
        ...,
        description="The natural-language reflection text (LLM-generated).",
    )
    done_count: int = Field(
        ...,
        ge=0,
        description="Commitments completed today (includes the recurring roll-forward heuristic).",
    )
    open_count: int = Field(
        ...,
        ge=0,
        description="Commitments still open at reflection time.",
    )
    abandoned_count: int = Field(
        ...,
        ge=0,
        description="Commitments abandoned today.",
    )
    generated_at: datetime = Field(
        ...,
        description="Timestamp when this reflection was generated.",
    )
    cached: bool = Field(
        default=False,
        description="True if the reflection came from cache, False if freshly generated.",
    )
