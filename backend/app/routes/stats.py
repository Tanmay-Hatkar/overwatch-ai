"""
stats.py — FastAPI routes for aggregate statistics.

  GET /stats/today
    Returns completion counts (today, this week), streak days, and a
    7-day daily completion series. Computed on demand from commitments;
    no caching at this scale.
"""

import sqlite3

from fastapi import APIRouter, Depends

from app.database import get_db
from app.models.stats import StatsResponse
from app.repositories.commitment_repository import CommitmentRepository
from app.services.commitment_service import CommitmentService
from app.services.stats_service import StatsService

router = APIRouter(prefix="/stats", tags=["stats"])


def _build_stats_service(
    conn: sqlite3.Connection = Depends(get_db),
) -> StatsService:
    """Construct a StatsService for one request."""
    repo = CommitmentRepository(conn)
    commitment_service = CommitmentService(repo)
    return StatsService(commitment_service)


@router.get("/today", response_model=StatsResponse)
def get_today_stats(
    service: StatsService = Depends(_build_stats_service),
) -> StatsResponse:
    """
    Returns today's stats: completion counts + 7-day series + streak.
    """
    return service.get_today_stats()
