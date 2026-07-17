"""
reflections.py — FastAPI routes for evening reflections.

  GET /reflections/today
    Returns today's reflection. Hits the cache if it's fresh; otherwise
    regenerates via LLM.

  GET /reflections/today?force_regenerate=true
    Skips the cache and always regenerates. Used by the UI's refresh button.

Mirrors app/routes/briefings.py exactly (same auth dependency, same
error-handling shape).
"""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, status

from app.database import get_db
from app.models.reflection import ReflectionResponse
from app.models.user import UserResponse
from app.repositories.commitment_repository import CommitmentRepository
from app.repositories.reflection_repository import ReflectionRepository
from app.routes.auth import current_user
from app.services.commitment_service import CommitmentService
from app.services.reflection_service import ReflectionGenerationError, ReflectionService
from app.services.timezone_utils import resolve_timezone

router = APIRouter(prefix="/reflections", tags=["reflections"])


def _build_reflection_service(
    conn: sqlite3.Connection = Depends(get_db),
) -> ReflectionService:
    """
    Construct a ReflectionService for one request.

    Resolves the full dependency chain:
        route -> _build_reflection_service -> get_db (yields connection)
        ReflectionService( CommitmentService(CommitmentRepository),
                           ReflectionRepository )

    The connection is automatically closed when the request finishes.
    """
    commitment_repo = CommitmentRepository(conn)
    commitment_service = CommitmentService(commitment_repo)
    reflection_repo = ReflectionRepository(conn)
    return ReflectionService(commitment_service, reflection_repo)


@router.get("/today", response_model=ReflectionResponse)
def get_today_reflection(
    force_regenerate: bool = False,
    timezone: str | None = None,
    user: UserResponse = Depends(current_user),
    service: ReflectionService = Depends(_build_reflection_service),
) -> ReflectionResponse:
    """
    Return the signed-in user's reflection for today.

    By default, returns the cached reflection if it's still fresh (no
    commitments have been updated since it was generated). Pass
    `?force_regenerate=true` to bypass the cache and call the LLM
    regardless.

    `?timezone=` is the browser's IANA timezone name (e.g.
    'America/Toronto') — determines what "today" means. Defaults to UTC
    if omitted.

    Returns 200 with the reflection, or 503 if the LLM is unavailable
    when a fresh generation is needed.
    """
    try:
        return service.get_today(
            user.id, force_regenerate=force_regenerate, user_tz=resolve_timezone(timezone)
        )
    except ReflectionGenerationError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not generate reflection: {e}",
        )
