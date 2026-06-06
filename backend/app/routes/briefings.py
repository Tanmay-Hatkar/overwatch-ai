"""
briefings.py — FastAPI routes for morning briefings.

  GET /briefings/today
    Returns today's briefing. Hits the cache if it's fresh; otherwise
    regenerates via LLM.

  GET /briefings/today?force_regenerate=true
    Skips the cache and always regenerates. Used by the UI's refresh button.

Auth required — every briefing is scoped to the signed-in user.
"""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, status

from app.database import get_db
from app.models.briefing import BriefingResponse
from app.models.user import UserResponse
from app.repositories.briefing_repository import BriefingRepository
from app.repositories.commitment_repository import CommitmentRepository
from app.routes.auth import current_user
from app.routes.calendar import get_calendar_service
from app.services.briefing_service import BriefingGenerationError, BriefingService
from app.services.calendar_service import CalendarService
from app.services.commitment_service import CommitmentService

router = APIRouter(prefix="/briefings", tags=["briefings"])


def _build_briefing_service(
    conn: sqlite3.Connection = Depends(get_db),
    calendar_service: CalendarService = Depends(get_calendar_service),
) -> BriefingService:
    """
    Construct a BriefingService for one request.

    Resolves the full dependency chain:
        route -> _build_briefing_service -> get_db (yields connection)
                                         -> get_calendar_service (singleton)
        BriefingService( CommitmentService(CommitmentRepository),
                         BriefingRepository,
                         CalendarService )

    The connection is automatically closed when the request finishes.
    The calendar service is a long-lived singleton (no per-request state).
    """
    commitment_repo = CommitmentRepository(conn)
    commitment_service = CommitmentService(commitment_repo)
    briefing_repo = BriefingRepository(conn)
    return BriefingService(commitment_service, briefing_repo, calendar_service)


@router.get("/today", response_model=BriefingResponse)
def get_today_briefing(
    force_regenerate: bool = False,
    user: UserResponse = Depends(current_user),
    service: BriefingService = Depends(_build_briefing_service),
) -> BriefingResponse:
    """
    Return today's briefing for the signed-in user.

    By default, returns the cached briefing if it's still fresh (no
    commitments have been updated since it was generated). Pass
    `?force_regenerate=true` to bypass the cache and call the LLM
    regardless.

    Returns 200 with the briefing, or 503 if the LLM is unavailable
    when a fresh generation is needed.
    """
    try:
        return service.get_today(user.id, force_regenerate=force_regenerate)
    except BriefingGenerationError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not generate briefing: {e}",
        )
