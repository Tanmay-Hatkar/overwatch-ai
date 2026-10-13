"""
goal.py — Pydantic schemas for weekly rate goals (ADR-0026).

A Goal is a count per calendar week ("10 job applications", "gym 4x").
It's the PRD §4.4 shape of a commitment: not "do X at time T" but "do X,
N times, this week". Progress resets each Monday (user-local) — there is
deliberately no history, carryover, or streak (ADR-0023).

  GoalCreate    - what POST /goals accepts
  GoalUpdate    - what PATCH /goals/{id} accepts (all optional)
  GoalLogCreate - what POST /goals/{id}/log accepts
  GoalResponse  - stored fields + this week's computed progress
"""

from datetime import date, datetime
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.config import settings


class GoalStatus(str, Enum):
    """Lifecycle of a goal. ARCHIVED goals are kept but not shown."""

    ACTIVE = "active"
    ARCHIVED = "archived"


# Where a goal stands this week, for the client to pick copy and visuals.
#   in_progress - still going, nothing to ask
#   check_in    - late in the week with some left: offer keep going / lower
#                 the target / call it good, once (the PRD §4.5 "Friday check")
#   met         - target reached
#   settled     - the user called this week good before reaching it
GoalWeekState = Literal["in_progress", "check_in", "met", "settled"]

# The user's answer to the end-of-week check-in. None clears it.
WeekDecision = Literal["keep_going", "call_it_good"]


class GoalCreate(BaseModel):
    """Body for POST /goals."""

    text: str = Field(..., min_length=1, max_length=200, description="What's being counted.")
    target_count: int = Field(
        ..., ge=1, le=settings.goal_max_target, description="How many times per week."
    )


class GoalUpdate(BaseModel):
    """Body for PATCH /goals/{id}. Only non-None fields change."""

    text: str | None = Field(default=None, min_length=1, max_length=200)
    target_count: int | None = Field(default=None, ge=1, le=settings.goal_max_target)
    status: GoalStatus | None = None


class GoalLogCreate(BaseModel):
    """Body for POST /goals/{id}/log."""

    amount: int = Field(default=1, ge=1, le=settings.goal_max_log_amount)


class GoalWeekDecisionRequest(BaseModel):
    """Body for POST /goals/{id}/week-decision."""

    decision: WeekDecision | None = Field(
        ..., description="'keep_going', 'call_it_good', or null to undo the choice."
    )


class GoalResponse(BaseModel):
    """A goal plus where it stands in the user's current week."""

    id: UUID
    text: str
    target_count: int
    status: GoalStatus
    created_at: datetime
    updated_at: datetime

    week_start: date = Field(..., description="Monday of the current week, user-local.")
    done_this_week: int = Field(..., ge=0)
    remaining: int = Field(..., ge=0, description="max(0, target - done).")
    days_left: int = Field(
        ..., ge=1, le=7, description="Days left in the week including today (Sun = 1)."
    )
    state: GoalWeekState

    model_config = ConfigDict(from_attributes=True)


class GoalRecord(BaseModel):
    """A goal row as stored — no week-relative progress. Repository output."""

    id: UUID
    text: str
    target_count: int
    status: GoalStatus
    decision: WeekDecision | None
    decision_week: date | None
    created_at: datetime
    updated_at: datetime
