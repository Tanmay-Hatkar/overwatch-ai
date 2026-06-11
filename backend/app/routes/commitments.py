"""
commitments.py — FastAPI routes for the Commitment resource.

Each handler is a thin shim: validate input, resolve the signed-in user via
`current_user`, call the service threading the user's id, return the result.

Every route requires authentication — there are no anonymous commitment
operations, and the service/repository scope all data by user_id.
"""

import sqlite3
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.database import get_db
from app.models.commitment import (
    CommitmentCreate,
    CommitmentParseRequest,
    CommitmentResponse,
    CommitmentStatus,
    CommitmentUpdate,
)
from app.models.user import UserResponse
from app.repositories.commitment_repository import CommitmentRepository
from app.routes.auth import current_user
from app.services.commitment_parser_service import (
    CommitmentParseError,
    CommitmentParserService,
)
from app.services.commitment_service import CommitmentService

router = APIRouter(prefix="/commitments", tags=["commitments"])


def _build_service(conn: sqlite3.Connection = Depends(get_db)) -> CommitmentService:
    """Construct a CommitmentService for one request."""
    return CommitmentService(CommitmentRepository(conn))


@router.post("", response_model=CommitmentResponse, status_code=status.HTTP_201_CREATED)
def create_commitment(
    payload: CommitmentCreate,
    user: UserResponse = Depends(current_user),
    service: CommitmentService = Depends(_build_service),
) -> CommitmentResponse:
    """Create a new commitment from structured input."""
    return service.create(user.id, payload)


@router.post("/parse", response_model=CommitmentResponse, status_code=status.HTTP_201_CREATED)
def parse_commitment(
    payload: CommitmentParseRequest,
    user: UserResponse = Depends(current_user),
    service: CommitmentService = Depends(_build_service),
) -> CommitmentResponse:
    """
    Create a commitment from natural language via LLM parsing.

    Returns 201 with the created commitment, or 503 if the LLM is unavailable
    or returns unparseable output.
    """
    parser = CommitmentParserService(service)
    try:
        return parser.parse_and_create(user.id, payload.message)
    except CommitmentParseError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not parse commitment: {e}",
        )


@router.get("", response_model=list[CommitmentResponse])
def list_commitments(
    status_filter: CommitmentStatus | None = None,
    user: UserResponse = Depends(current_user),
    service: CommitmentService = Depends(_build_service),
) -> list[CommitmentResponse]:
    """List the signed-in user's commitments, optionally filtered by status."""
    return service.list(user.id, status=status_filter)


@router.get("/{commitment_id}", response_model=CommitmentResponse)
def get_commitment(
    commitment_id: UUID,
    user: UserResponse = Depends(current_user),
    service: CommitmentService = Depends(_build_service),
) -> CommitmentResponse:
    """Fetch one of the user's commitments by id (404 if not theirs)."""
    commitment = service.get(user.id, commitment_id)
    if commitment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Commitment {commitment_id} not found",
        )
    return commitment


@router.patch("/{commitment_id}", response_model=CommitmentResponse)
def update_commitment(
    commitment_id: UUID,
    payload: CommitmentUpdate,
    user: UserResponse = Depends(current_user),
    service: CommitmentService = Depends(_build_service),
) -> CommitmentResponse:
    """Partially update a commitment (text, due_at, and/or status)."""
    commitment = service.update(user.id, commitment_id, payload)
    if commitment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Commitment {commitment_id} not found",
        )
    return commitment


@router.delete("/{commitment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_commitment(
    commitment_id: UUID,
    user: UserResponse = Depends(current_user),
    service: CommitmentService = Depends(_build_service),
) -> None:
    """Hard-delete one of the user's commitments by id."""
    if not service.delete(user.id, commitment_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Commitment {commitment_id} not found",
        )
