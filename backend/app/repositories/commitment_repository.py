"""
commitment_repository.py — Data access for the Commitment entity.

The repository owns all SQL for Commitments. No business logic lives here —
just reads, writes, and conversions between database rows and domain objects.

Multi-tenancy (slice 12): every method takes a user_id as its first
parameter. Reads filter by it; writes stamp it. There is no "all users"
path — that boundary is the safety net against cross-tenant leaks.
"""

import sqlite3
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.models.commitment import CommitmentResponse, CommitmentStatus, Recurrence


class CommitmentRepository:
    """Data access class for Commitment records (scoped by user_id)."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        """
        Args:
            conn: An open SQLite connection. The repository does NOT manage
                the connection lifecycle (caller owns it).
        """
        self._conn = conn

    def create(
        self,
        user_id: UUID,
        text: str,
        due_at: datetime | None,
        recurrence: str = "none",
        reminder_lead_minutes: int = 0,
    ) -> CommitmentResponse:
        """
        Insert a new commitment owned by user_id.

        Args:
            user_id: Owner of the commitment.
            text: The commitment statement.
            due_at: Optional due timestamp.
            recurrence: 'none' | 'daily' | 'weekly'.
            reminder_lead_minutes: Minutes before due_at to nudge (0 = exact).

        Returns:
            The newly created commitment.
        """
        new_id = str(uuid4())
        now = datetime.now(UTC).isoformat()
        due_at_str = due_at.isoformat() if due_at is not None else None
        status = CommitmentStatus.OPEN.value

        self._conn.execute(
            """
            INSERT INTO commitments
                (id, user_id, text, due_at, status, recurrence, reminder_lead_minutes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (new_id, str(user_id), text, due_at_str, status, recurrence,
             reminder_lead_minutes, now, now),
        )
        self._conn.commit()

        result = self.get(user_id, UUID(new_id))
        assert result is not None, "Just-inserted commitment unexpectedly missing"
        return result

    def get(self, user_id: UUID, commitment_id: UUID) -> CommitmentResponse | None:
        """
        Fetch one commitment by id, scoped to its owner.

        A commitment owned by a different user is invisible (returns None) —
        the right default for a multi-tenant system.
        """
        row = self._conn.execute(
            "SELECT * FROM commitments WHERE id = ? AND user_id = ?",
            (str(commitment_id), str(user_id)),
        ).fetchone()
        return self._row_to_response(row) if row is not None else None

    def list(
        self, user_id: UUID, status: CommitmentStatus | None = None
    ) -> list[CommitmentResponse]:
        """
        List a user's commitments, optionally filtered by status, newest first.
        """
        if status is not None:
            rows = self._conn.execute(
                """
                SELECT * FROM commitments
                 WHERE user_id = ? AND status = ?
                 ORDER BY created_at DESC
                """,
                (str(user_id), status.value),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM commitments WHERE user_id = ? ORDER BY created_at DESC",
                (str(user_id),),
            ).fetchall()
        return [self._row_to_response(row) for row in rows]

    def update(
        self,
        user_id: UUID,
        commitment_id: UUID,
        text: str | None = None,
        due_at: datetime | None = None,
        status: CommitmentStatus | None = None,
        recurrence: str | None = None,
        reminder_lead_minutes: int | None = None,
    ) -> CommitmentResponse | None:
        """
        Partial update of a commitment, scoped to its owner.

        Only non-None fields are changed. To explicitly clear a due date,
        pass clear_due_at via the service (see CommitmentUpdate handling).

        Returns:
            The updated commitment, or None if no such commitment for this user.
        """
        existing = self.get(user_id, commitment_id)
        if existing is None:
            return None

        updates: dict[str, object] = {}
        if text is not None:
            updates["text"] = text
        if due_at is not None:
            updates["due_at"] = due_at.isoformat()
        if status is not None:
            updates["status"] = status.value
        if recurrence is not None:
            updates["recurrence"] = recurrence
        if reminder_lead_minutes is not None:
            updates["reminder_lead_minutes"] = reminder_lead_minutes

        if not updates:
            return existing

        updates["updated_at"] = datetime.now(UTC).isoformat()

        set_clause = ", ".join(f"{key} = ?" for key in updates)
        values = list(updates.values()) + [str(commitment_id), str(user_id)]
        self._conn.execute(
            f"UPDATE commitments SET {set_clause} WHERE id = ? AND user_id = ?",
            values,
        )
        self._conn.commit()
        return self.get(user_id, commitment_id)

    def set_due_at(
        self, user_id: UUID, commitment_id: UUID, due_at: datetime | None
    ) -> CommitmentResponse | None:
        """
        Set or CLEAR the due date explicitly (None clears it).

        Separate from update() because update() treats None as "leave
        unchanged"; this method treats None as "remove the due date".
        """
        existing = self.get(user_id, commitment_id)
        if existing is None:
            return None
        due_str = due_at.isoformat() if due_at is not None else None
        now = datetime.now(UTC).isoformat()
        self._conn.execute(
            "UPDATE commitments SET due_at = ?, updated_at = ? WHERE id = ? AND user_id = ?",
            (due_str, now, str(commitment_id), str(user_id)),
        )
        self._conn.commit()
        return self.get(user_id, commitment_id)

    def latest_update_time(self, user_id: UUID) -> datetime | None:
        """Most recent updated_at across this user's commitments, or None."""
        row = self._conn.execute(
            "SELECT MAX(updated_at) AS latest FROM commitments WHERE user_id = ?",
            (str(user_id),),
        ).fetchone()
        if row is None or row["latest"] is None:
            return None
        return datetime.fromisoformat(row["latest"])

    def delete(self, user_id: UUID, commitment_id: UUID) -> bool:
        """Hard-delete a commitment by id, scoped to its owner."""
        cursor = self._conn.execute(
            "DELETE FROM commitments WHERE id = ? AND user_id = ?",
            (str(commitment_id), str(user_id)),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    @staticmethod
    def _row_to_response(row: sqlite3.Row) -> CommitmentResponse:
        """Convert a sqlite3.Row to a CommitmentResponse."""
        # `recurrence`/`reminder_lead_minutes` were added in later migrations;
        # default safely if a raw row mapping predates them.
        keys = row.keys()
        recurrence = row["recurrence"] if "recurrence" in keys else "none"
        lead = row["reminder_lead_minutes"] if "reminder_lead_minutes" in keys else 0
        return CommitmentResponse(
            id=UUID(row["id"]),
            text=row["text"],
            due_at=(
                datetime.fromisoformat(row["due_at"])
                if row["due_at"] is not None
                else None
            ),
            status=CommitmentStatus(row["status"]),
            recurrence=Recurrence(recurrence or "none"),
            reminder_lead_minutes=lead if lead is not None else 0,
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
