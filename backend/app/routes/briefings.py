"""
briefings.py — FastAPI routes for morning briefings.

Currently one endpoint:

  GET /briefings/today
    Generates a fresh briefing for the current day. Returns 200 with the
    briefing, or 503 if the LLM is unavailable.

No caching in slice 4 — every request hits the LLM. Future slices can
add a `briefings` table + per-day caching with a regenerate endpoint.
"""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, status

from app.database import get_db
from app.models.briefing import BriefingResponse
from app.repositories.commitment_repository import CommitmentRepository
from app.services.briefing_service import BriefingGenerationError, BriefingService
from app.services.commitment_service import CommitmentService

router = APIRouter(prefix="/briefings", tags=["briefings"])


def _build_briefing_service(
    conn: sqlite3.Connection = Depends(get_db),
) -> BriefingService:
    """
    Construct a BriefingService for one request.

    FastAPI resolves the dependency chain:
        route -> _build_briefing_service -> get_db (yields connection).

    The connection is automatically closed when the request finishes.
    """
    repo = CommitmentRepository(conn)
    commitment_service = CommitmentService(repo)
    return BriefingService(commitment_service)


@router.get("/today", response_model=BriefingResponse)
def get_today_briefing(
    service: BriefingService = Depends(_build_briefing_service),
) -> BriefingResponse:
    """
    Generate a natural-language briefing for today.

    Pulls all open commitments, buckets them by due-date status, and asks
    the LLM to summarize. Returns 200 with the briefing, or 503 if the
    LLM is unavailable.
    """
    try:
        return service.generate_today()
    except BriefingGenerationError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not generate briefing: {e}",
        )
