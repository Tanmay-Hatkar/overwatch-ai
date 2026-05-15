"""
commitment_service.py — Business logic layer for Commitments.

The service sits between routes (HTTP) and the repository (data access).
For slice 1 it is mostly delegation, but it exists for three reasons:

  1. Routes stay thin — they just translate HTTP <-> service calls.
  2. Future business logic (scheduling, reconciliation, side effects)
     has a clear home that isn't a route handler or a SQL query.
  3. Tests can mock the repository when testing service logic, and mock
     the service when testing routes. Each layer is testable in isolation.

The service accepts Pydantic input models (CommitmentCreate, CommitmentUpdate)
from routes and returns Pydantic response models. The repository deals in
primitives. The service is the conversion seam between them.
"""

import logging
from uuid import UUID

from app.models.commitment import (
    CommitmentCreate,
    CommitmentResponse,
    CommitmentStatus,
    CommitmentUpdate,
)
from app.repositories.commitment_repository import CommitmentRepository

logger = logging.getLogger(__name__)


class CommitmentService:
    """
    Business logic for Commitments.

    Constructed with a CommitmentRepository — uses composition, not inheritance,
    so the repository can be swapped (e.g., a fake repo in tests) without
    changing the service.
    """

    def __init__(self, repo: CommitmentRepository) -> None:
        """
        Args:
            repo: An initialized CommitmentRepository instance.
        """
        self._repo = repo

    def create(self, payload: CommitmentCreate) -> CommitmentResponse:
        """
        Create a new commitment from a validated input payload.

        Args:
            payload: CommitmentCreate with text and optional due_at.

        Returns:
            The newly created commitment.
        """
        logger.info("Creating commitment: %r", payload.text[:50])
        return self._repo.create(text=payload.text, due_at=payload.due_at)

    def get(self, commitment_id: UUID) -> CommitmentResponse | None:
        """
        Fetch a commitment by id.

        Args:
            commitment_id: The UUID of the commitment.

        Returns:
            The commitment, or None if not found.
        """
        return self._repo.get(commitment_id)

    def list(self, status: CommitmentStatus | None = None) -> list[CommitmentResponse]:
        """
        List commitments, optionally filtered by status.

        Args:
            status: If provided, only return commitments in that status.

        Returns:
            List of commitments, most recent first. Empty list if none.
        """
        return self._repo.list(status=status)

    def update(
        self,
        commitment_id: UUID,
        payload: CommitmentUpdate,
    ) -> CommitmentResponse | None:
        """
        Apply a partial update to a commitment.

        Only fields present in the payload (non-None) are changed.

        Args:
            commitment_id: The UUID of the commitment.
            payload: CommitmentUpdate with optional text, due_at, status.

        Returns:
            The updated commitment, or None if no commitment with that id exists.
        """
        logger.info("Updating commitment %s", commitment_id)
        return self._repo.update(
            commitment_id,
            text=payload.text,
            due_at=payload.due_at,
            status=payload.status,
        )

    def delete(self, commitment_id: UUID) -> bool:
        """
        Hard-delete a commitment by id.

        Args:
            commitment_id: The UUID of the commitment.

        Returns:
            True if the commitment was deleted, False if it didn't exist.
        """
        logger.info("Deleting commitment %s", commitment_id)
        return self._repo.delete(commitment_id)
