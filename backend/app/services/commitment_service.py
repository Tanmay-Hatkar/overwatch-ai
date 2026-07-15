"""
commitment_service.py — Business logic layer for Commitments.

Sits between routes (HTTP) and the repository (data access). Every method
takes a user_id first, threaded from the `current_user` route dependency,
so all data access is scoped to the signed-in user (slice 12).

Note: uses `from __future__ import annotations` (PEP 563) so that the
`list[CommitmentResponse]` return-type annotations on the stale-check
query methods (added after the pre-existing `list()` method, which shadows
the builtin `list` within this class body) aren't evaluated eagerly.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
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
                rolled = self._repo.update(
                    user_id,
                    commitment_id,
                    due_at=next_due,
                    status=CommitmentStatus.OPEN,
                )
                # A rolled-forward occurrence is a new instance, not the same
                # dormant plan — clear any stale-check state so the new
                # occurrence starts fresh (ADR-0017).
                self._repo.clear_stale_check(user_id, commitment_id)
                return rolled

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

    # ------------------------------------------------------------------
    # Stale-plan detection (ADR-0017)
    # ------------------------------------------------------------------

    def list_stale_candidates(
        self, user_id: UUID, updated_before: datetime, today: date
    ) -> list[CommitmentResponse]:
        """Open, dormant commitments eligible for a one-time check-in."""
        return self._repo.list_stale_candidates(user_id, updated_before, today)

    def mark_stale_check_sent(self, user_id: UUID, commitment_id: UUID) -> None:
        """Record that we've asked "still the plan?" about this commitment."""
        self._repo.mark_stale_check_sent(user_id, commitment_id)

    def list_pending_stale_checks(self, user_id: UUID) -> list[CommitmentResponse]:
        """Commitments asked about whose reply hasn't been processed yet."""
        return self._repo.list_pending_stale_checks(user_id)

    def acknowledge_stale_check(self, user_id: UUID, commitment_id: UUID) -> None:
        """Mark a pending stale check-in as resolved, so it's not re-intercepted."""
        self._repo.mark_stale_check_acknowledged(user_id, commitment_id)
