"""
commitments.py — FastAPI routes for the Commitment resource.

Each handler is a thin shim that:

  1. Receives the HTTP request (path/query params validated by FastAPI,
     body validated by Pydantic).
  2. Resolves the signed-in user via the `current_user` dependency.
  3. Calls the appropriate service method, threading the user's id.
  4. Returns the response, or raises HTTPException for error cases.

No SQL lives here. No business logic lives here. Routes are translation
between HTTP and the service layer.

Every route here requires authentication — there are no anonymous
commitment operations.
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
    """
    Construct a CommitmentService for one request.

    FastAPI calls this as a dependency. It resolves the chain:
        route -> _build_service -> get_db (yields connection)

    The connection is automatically closed when the request finishes.
    """
    repo = CommitmentRepository(conn)
    return CommitmentService(repo)


@router.post("", response_model=CommitmentResponse, status_code=status.HTTP_201_CREATED)
def create_commitment(
    payload: CommitmentCreate,
    user: UserResponse = Depends(current_user),
    service: CommitmentService = Depends(_build_service),
) -> CommitmentResponse:
    """
    Create a new commitment from structured input.

    Returns 201 with the created commitment in the body.
    """
    return service.create(user.id, payload)


@router.post("/parse", response_model=CommitmentResponse, status_code=status.HTTP_201_CREATED)
def parse_commitment(
    payload: CommitmentParseRequest,
    user: UserResponse = Depends(current_user),
    service: CommitmentService = Depends(_build_service),
) -> CommitmentResponse:
    """
    Create a commitment from natural language via LLM parsing.

    Body: {"message": "remind me to call mom tomorrow at 3pm"}
    The LLM extracts the imperative text + optional due_at and creates
    the commitment.

    Returns 201 with the created commitment, or 503 if the LLM is
    unavailable or returns unparseable output.
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
    """
    List the signed-in user's commitments, optionally filtered by status.

    Query param `status_filter` accepts "open", "done", or "abandoned".
    Returns 200 with a JSON array (possibly empty).
    """
    return service.list(user.id, status=status_filter)


@router.get("/{commitment_id}", response_model=CommitmentResponse)
def get_commitment(
    commitment_id: UUID,
    user: UserResponse = Depends(current_user),
    service: CommitmentService = Depends(_build_service),
) -> CommitmentResponse:
    """
    Fetch a single commitment by id (must be owned by the signed-in user).

    Returns 200 with the commitment, or 404 if not found / owned by someone else.
    """
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
    """
    Partially update a commitment. Only fields present in the body are changed.

    Returns 200 with the updated commitment, or 404 if not found / owned by someone else.
    """
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
    """
    Hard-delete a commitment by id.

    Returns 204 with no body on success, 404 if not found / owned by someone else.
    """
    deleted = service.delete(user.id, commitment_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Commitment {commitment_id} not found",
        )
