"""
commitment_service.py — Business logic layer for Commitments.

The service sits between routes (HTTP) and the repository (data access).
For slice 1 it is mostly delegation, but it exists for three reasons:

  1. Routes stay thin — they just translate HTTP <-> service calls.
  2. Future business logic (scheduling, reconciliation, side effects)
     has a clear home that isn't a route handler or a SQL query.
  3. Tests can mock the repository when testing service logic, and mock
     the service when testing routes. Each layer is testable in isolation.

Every method takes a user_id as its first parameter, threaded through
from the `current_user` route dependency. The repository enforces the
WHERE user_id = ? filter on every SQL query, so passing the wrong id
returns "no such commitment" rather than leaking cross-tenant data.
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

    def create(self, user_id: UUID, payload: CommitmentCreate) -> CommitmentResponse:
        """
        Create a new commitment owned by the given user.

        Args:
            user_id: Owner of the new commitment.
            payload: CommitmentCreate with text and optional due_at.

        Returns:
            The newly created commitment.
        """
        logger.info("Creating commitment for user %s: %r", user_id, payload.text[:50])
        return self._repo.create(user_id=user_id, text=payload.text, due_at=payload.due_at)

    def get(self, user_id: UUID, commitment_id: UUID) -> CommitmentResponse | None:
        """
        Fetch a commitment by id, scoped to its owner.

        Args:
            user_id: Owner of the commitment.
            commitment_id: The UUID of the commitment.

        Returns:
            The commitment, or None if not found / owned by someone else.
        """
        return self._repo.get(user_id, commitment_id)

    def list(
        self,
        user_id: UUID,
        status: CommitmentStatus | None = None,
    ) -> list[CommitmentResponse]:
        """
        List a user's commitments, optionally filtered by status.

        Args:
            user_id: Owner whose commitments to return.
            status: If provided, only return commitments in that status.

        Returns:
            List of commitments, most recent first. Empty list if none.
        """
        return self._repo.list(user_id, status=status)

    def update(
        self,
        user_id: UUID,
        commitment_id: UUID,
        payload: CommitmentUpdate,
    ) -> CommitmentResponse | None:
        """
        Apply a partial update to a commitment, scoped to its owner.

        Only fields present in the payload (non-None) are changed.

        Args:
            user_id: Owner of the commitment.
            commitment_id: The UUID of the commitment.
            payload: CommitmentUpdate with optional text, due_at, status.

        Returns:
            The updated commitment, or None if no commitment with that id
            exists for this user.
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
        """
        Get the timestamp of the most recently updated commitment for this user.

        Used by BriefingService for cache freshness — if any of this user's
        commitments has been touched since their cached briefing was
        generated, the cache is stale for them.

        Returns:
            The latest updated_at timestamp, or None if the user has no
            commitments at all.
        """
        return self._repo.latest_update_time(user_id)

    def delete(self, user_id: UUID, commitment_id: UUID) -> bool:
        """
        Hard-delete a commitment by id, scoped to its owner.

        Args:
            user_id: Owner of the commitment.
            commitment_id: The UUID of the commitment.

        Returns:
            True if the commitment was deleted, False if it didn't exist
            or wasn't owned by this user.
        """
        logger.info("Deleting commitment %s (user %s)", commitment_id, user_id)
        return self._repo.delete(user_id, commitment_id)
