"""
goals.py — FastAPI routes for weekly rate goals (ADR-0026).

  GET    /goals                        active goals + this week's progress
  POST   /goals                        create
  PATCH  /goals/{id}                   rename / change target / archive
  DELETE /goals/{id}                   hard-delete (logs go with it)
  POST   /goals/{id}/log               add progress (default +1)
  DELETE /goals/{id}/log               undo this week's most recent log
  POST   /goals/{id}/week-decision     answer the end-of-week check-in

Every route takes `?timezone=` (IANA name): "this week" is the user's
local Monday-to-Sunday. Missing or unknown falls back to UTC.
"""

import sqlite3
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.database import get_db
from app.models.goal import (
    GoalCreate,
    GoalLogCreate,
    GoalResponse,
    GoalUpdate,
    GoalWeekDecisionRequest,
)
from app.models.user import UserResponse
from app.repositories.goal_repository import GoalRepository
from app.routes.auth import current_user
from app.services.goal_service import GoalService
from app.services.timezone_utils import resolve_timezone

router = APIRouter(prefix="/goals", tags=["goals"])


def _build_service(conn: sqlite3.Connection = Depends(get_db)) -> GoalService:
    """Construct a GoalService for one request."""
    return GoalService(GoalRepository(conn))


def _found(goal: GoalResponse | None, goal_id: UUID) -> GoalResponse:
    """Return the goal, or raise 404 if the service found nothing."""
    if goal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Goal {goal_id} not found")
    return goal


@router.get("", response_model=list[GoalResponse])
def list_goals(
    timezone: str | None = None,
    user: UserResponse = Depends(current_user),
    service: GoalService = Depends(_build_service),
) -> list[GoalResponse]:
    """List the signed-in user's active goals with this week's progress."""
    return service.list(user.id, resolve_timezone(timezone))


@router.post("", response_model=GoalResponse, status_code=status.HTTP_201_CREATED)
def create_goal(
    payload: GoalCreate,
    timezone: str | None = None,
    user: UserResponse = Depends(current_user),
    service: GoalService = Depends(_build_service),
) -> GoalResponse:
    """Create a weekly goal."""
    return service.create(user.id, payload, resolve_timezone(timezone))


@router.patch("/{goal_id}", response_model=GoalResponse)
def update_goal(
    goal_id: UUID,
    payload: GoalUpdate,
    timezone: str | None = None,
    user: UserResponse = Depends(current_user),
    service: GoalService = Depends(_build_service),
) -> GoalResponse:
    """Rename a goal, change its weekly target, or archive it."""
    return _found(service.update(user.id, goal_id, payload, resolve_timezone(timezone)), goal_id)


@router.delete("/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_goal(
    goal_id: UUID,
    user: UserResponse = Depends(current_user),
    service: GoalService = Depends(_build_service),
) -> None:
    """Hard-delete a goal and its progress logs."""
    if not service.delete(user.id, goal_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Goal {goal_id} not found")


@router.post("/{goal_id}/log", response_model=GoalResponse)
def log_progress(
    goal_id: UUID,
    payload: GoalLogCreate,
    timezone: str | None = None,
    user: UserResponse = Depends(current_user),
    service: GoalService = Depends(_build_service),
) -> GoalResponse:
    """Add progress toward a goal (default +1)."""
    return _found(service.log(user.id, goal_id, payload.amount, resolve_timezone(timezone)), goal_id)


@router.delete("/{goal_id}/log", response_model=GoalResponse)
def undo_progress(
    goal_id: UUID,
    timezone: str | None = None,
    user: UserResponse = Depends(current_user),
    service: GoalService = Depends(_build_service),
) -> GoalResponse:
    """Undo this week's most recent progress log (no-op if there is none)."""
    return _found(service.undo_last_log(user.id, goal_id, resolve_timezone(timezone)), goal_id)


@router.post("/{goal_id}/week-decision", response_model=GoalResponse)
def decide_week(
    goal_id: UUID,
    payload: GoalWeekDecisionRequest,
    timezone: str | None = None,
    user: UserResponse = Depends(current_user),
    service: GoalService = Depends(_build_service),
) -> GoalResponse:
    """Answer the end-of-week check-in: keep going, or call this week good."""
    return _found(
        service.decide_week(user.id, goal_id, payload.decision, resolve_timezone(timezone)), goal_id
    )
