"""
commitment_repository.py — Data access for the Commitment entity.

The repository owns all SQL for Commitments. No business logic lives here —
just reads, writes, and conversions between database rows and domain objects.
Other layers (services, routes) call the repository; they never write SQL.

This is the Repository Pattern: encapsulate data access behind a stable
interface so the rest of the codebase doesn't depend on storage details.

Multi-tenancy: every method takes a user_id as its first parameter. The
repository transparently filters reads and stamps writes with that id.
There is no "list everything across users" path — that boundary is the
safety net against accidental cross-tenant data leaks.
"""

import sqlite3
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.models.commitment import CommitmentResponse, CommitmentStatus


class CommitmentRepository:
    """
    Data access class for Commitment records.

    Construct with an open SQLite connection. Each method performs one
    database operation. Returns CommitmentResponse Pydantic models for
    consistency with the API layer.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        """
        Args:
            conn: An open SQLite connection. The repository does NOT
                manage the connection lifecycle (caller owns it).
        """
        self._conn = conn

    def create(
        self, user_id: UUID, text: str, due_at: datetime | None
    ) -> CommitmentResponse:
        """
        Insert a new commitment row owned by the given user.

        Args:
            user_id: Owner of the commitment.
            text: The commitment statement.
            due_at: Optional due timestamp.

        Returns:
            The newly created commitment as a CommitmentResponse.
        """
        new_id = str(uuid4())
        now = datetime.now(UTC).isoformat()
        due_at_str = due_at.isoformat() if due_at is not None else None
        status = CommitmentStatus.OPEN.value

        self._conn.execute(
            """
            INSERT INTO commitments (id, user_id, text, due_at, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (new_id, str(user_id), text, due_at_str, status, now, now),
        )
        self._conn.commit()

        result = self.get(user_id, UUID(new_id))
        assert result is not None, "Just-inserted commitment unexpectedly missing"
        return result

    def get(self, user_id: UUID, commitment_id: UUID) -> CommitmentResponse | None:
        """
        Fetch a single commitment by id, scoped to its owner.

        A commitment belonging to a different user is invisible — same
        behavior as if it didn't exist. This is the right default for
        a multi-tenant system.

        Args:
            user_id: Owner of the commitment.
            commitment_id: The UUID of the commitment.

        Returns:
            The commitment as a CommitmentResponse, or None if not found
            (or owned by a different user).
        """
        row = self._conn.execute(
            "SELECT * FROM commitments WHERE id = ? AND user_id = ?",
            (str(commitment_id), str(user_id)),
        ).fetchone()
        return self._row_to_response(row) if row is not None else None

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
            List of CommitmentResponse, sorted by created_at descending
            (most recent first). Empty list if no matches.
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
                """
                SELECT * FROM commitments
                 WHERE user_id = ?
                 ORDER BY created_at DESC
                """,
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
    ) -> CommitmentResponse | None:
        """
        Partial update of a commitment. Only non-None fields are changed.

        Args:
            user_id: Owner of the commitment.
            commitment_id: The UUID of the commitment to update.
            text: Optional new text.
            due_at: Optional new due timestamp.
            status: Optional new status.

        Returns:
            The updated CommitmentResponse, or None if no commitment with
            that id exists for this user.
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

    def latest_update_time(self, user_id: UUID) -> datetime | None:
        """
        Return the most recent updated_at across this user's commitments.

        Used by BriefingService to detect when its cached briefing is stale.
        """
        row = self._conn.execute(
            "SELECT MAX(updated_at) AS latest FROM commitments WHERE user_id = ?",
            (str(user_id),),
        ).fetchone()
        if row is None or row["latest"] is None:
            return None
        return datetime.fromisoformat(row["latest"])

    def delete(self, user_id: UUID, commitment_id: UUID) -> bool:
        """
        Hard-delete a commitment by id, scoped to its owner.

        Args:
            user_id: Owner of the commitment.
            commitment_id: The UUID of the commitment to delete.

        Returns:
            True if a row was deleted, False if no such commitment exists
            for this user.
        """
        cursor = self._conn.execute(
            "DELETE FROM commitments WHERE id = ? AND user_id = ?",
            (str(commitment_id), str(user_id)),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    @staticmethod
    def _row_to_response(row: sqlite3.Row) -> CommitmentResponse:
        """
        Convert a sqlite3.Row to a CommitmentResponse.

        Handles type conversions: UUID from string, datetime from ISO string,
        enum from string value.
        """
        return CommitmentResponse(
            id=UUID(row["id"]),
            text=row["text"],
            due_at=(
                datetime.fromisoformat(row["due_at"])
                if row["due_at"] is not None
                else None
            ),
            status=CommitmentStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
