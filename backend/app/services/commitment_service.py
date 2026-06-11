"""
commitment_service.py — Business logic layer for Commitments.

Sits between routes (HTTP) and the repository (data access). Every method
takes a user_id first, threaded from the `current_user` route dependency,
so all data access is scoped to the signed-in user (slice 12).
"""

import logging
from datetime import datetime
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
    """Business logic for Commitments (scoped by user_id)."""

    def __init__(self, repo: CommitmentRepository) -> None:
        self._repo = repo

    def create(self, user_id: UUID, payload: CommitmentCreate) -> CommitmentResponse:
        """Create a new commitment owned by user_id."""
        logger.info("Creating commitment for user %s: %r", user_id, payload.text[:50])
        return self._repo.create(user_id=user_id, text=payload.text, due_at=payload.due_at)

    def get(self, user_id: UUID, commitment_id: UUID) -> CommitmentResponse | None:
        """Fetch a commitment by id, scoped to its owner."""
        return self._repo.get(user_id, commitment_id)

    def list(
        self, user_id: UUID, status: CommitmentStatus | None = None
    ) -> list[CommitmentResponse]:
        """List a user's commitments, optionally filtered by status."""
        return self._repo.list(user_id, status=status)

    def update(
        self,
        user_id: UUID,
        commitment_id: UUID,
        payload: CommitmentUpdate,
    ) -> CommitmentResponse | None:
        """
        Apply a partial update, scoped to the owner. Only non-None fields in
        the payload change — so the edit UI can reschedule (new due_at), rename
        (new text), or mark done (new status).
        """
        logger.info("Updating commitment %s (user %s)", commitment_id, user_id)
        return self._repo.update(
            user_id,
            commitment_id,
            text=payload.text,
            due_at=payload.due_at,
            status=payload.status,
        )

    def latest_commitment_update(self, user_id: UUID) -> datetime | None:
        """Timestamp of this user's most recently updated commitment, or None."""
        return self._repo.latest_update_time(user_id)

    def delete(self, user_id: UUID, commitment_id: UUID) -> bool:
        """Hard-delete a commitment by id, scoped to its owner."""
        logger.info("Deleting commitment %s (user %s)", commitment_id, user_id)
        return self._repo.delete(user_id, commitment_id)
