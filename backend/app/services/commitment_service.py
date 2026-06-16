"""
commitment_service.py — Business logic layer for Commitments.

Sits between routes (HTTP) and the repository (data access). Every method
takes a user_id first, threaded from the `current_user` route dependency,
so all data access is scoped to the signed-in user (slice 12).
"""

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.models.commitment import (
    CommitmentCreate,
    CommitmentResponse,
    CommitmentStatus,
    CommitmentUpdate,
    Recurrence,
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
        return self._repo.create(
            user_id=user_id,
            text=payload.text,
            due_at=payload.due_at,
            recurrence=payload.recurrence.value,
            reminder_lead_minutes=payload.reminder_lead_minutes,
        )

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

        # Completing a RECURRING commitment doesn't close it — it rolls forward
        # to the next occurrence and stays open. So a daily routine reappears
        # tomorrow instead of vanishing when you tick it off tonight.
        if payload.status == CommitmentStatus.DONE:
            existing = self._repo.get(user_id, commitment_id)
            if (
                existing is not None
                and existing.recurrence != Recurrence.NONE
                and existing.due_at is not None
            ):
                next_due = self._next_occurrence(existing.due_at, existing.recurrence)
                logger.info(
                    "Recurring commitment %s rolled forward to %s", commitment_id, next_due
                )
                return self._repo.update(
                    user_id,
                    commitment_id,
                    due_at=next_due,
                    status=CommitmentStatus.OPEN,
                )

        return self._repo.update(
            user_id,
            commitment_id,
            text=payload.text,
            due_at=payload.due_at,
            status=payload.status,
            recurrence=payload.recurrence.value if payload.recurrence is not None else None,
            reminder_lead_minutes=payload.reminder_lead_minutes,
        )

    @staticmethod
    def _next_occurrence(due_at: datetime, recurrence: Recurrence) -> datetime:
        """
        The next future occurrence after `due_at` for a daily/weekly recurrence.

        Advances by the period until the result is in the future, so a routine
        that was overdue for several days still lands on its next real slot.
        """
        delta = timedelta(days=1) if recurrence == Recurrence.DAILY else timedelta(days=7)
        nxt = due_at + delta
        now = datetime.now(UTC)
        while nxt <= now:
            nxt += delta
        return nxt

    def latest_commitment_update(self, user_id: UUID) -> datetime | None:
        """Timestamp of this user's most recently updated commitment, or None."""
        return self._repo.latest_update_time(user_id)

    def delete(self, user_id: UUID, commitment_id: UUID) -> bool:
        """Hard-delete a commitment by id, scoped to its owner."""
        logger.info("Deleting commitment %s (user %s)", commitment_id, user_id)
        return self._repo.delete(user_id, commitment_id)
