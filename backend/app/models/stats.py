"""
stats.py — Pydantic schemas for the /stats endpoint.

We compute stats from the commitments table (no separate stats table).
"completed at" is approximated by `updated_at` on done commitments —
imperfect (a text edit to a done item shifts its apparent completion
time) but adequate for MVP. A future migration can add a proper
`completed_at` column.
"""

from pydantic import BaseModel, Field


class DailyCompletion(BaseModel):
    """One day's completion count, used for the 7-day sparkline."""

    date: str = Field(..., description='ISO date, "YYYY-MM-DD"')
    count: int = Field(..., ge=0, description="Number of commitments completed on that day")


class StatsResponse(BaseModel):
    """Aggregate statistics for the /stats/today endpoint."""

    completed_today: int = Field(..., ge=0, description="Commitments marked done today")
    completed_this_week: int = Field(
        ..., ge=0, description="Commitments marked done in the last 7 days (inclusive of today)"
    )
    streak_days: int = Field(
        ...,
        ge=0,
        description=(
            "Consecutive days (ending today or yesterday) where at least one "
            "commitment was completed. 0 if neither today nor yesterday had a completion."
        ),
    )
    daily_completions: list[DailyCompletion] = Field(
        ...,
        description="Last 7 days of completion counts, oldest first. Length is always 7.",
    )
