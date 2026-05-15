"""
commitment_repository.py — Data access for the Commitment entity.

The repository owns all SQL for Commitments. No business logic lives here —
just reads, writes, and conversions between database rows and domain objects.
Other layers (services, routes) call the repository; they never write SQL.

This is the Repository Pattern: encapsulate data access behind a stable
interface so the rest of the codebase doesn't depend on storage details.
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

    def create(self, text: str, due_at: datetime | None) -> CommitmentResponse:
        """
        Insert a new commitment row. Server assigns id, status='open',
        and the created_at/updated_at timestamps.

        Args:
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
            INSERT INTO commitments (id, text, due_at, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (new_id, text, due_at_str, status, now, now),
        )
        self._conn.commit()

        # We just inserted it; get() should never return None here.
        result = self.get(UUID(new_id))
        assert result is not None, "Just-inserted commitment unexpectedly missing"
        return result

    def get(self, commitment_id: UUID) -> CommitmentResponse | None:
        """
        Fetch a single commitment by id.

        Args:
            commitment_id: The UUID of the commitment.

        Returns:
            The commitment as a CommitmentResponse, or None if not found.
        """
        row = self._conn.execute(
            "SELECT * FROM commitments WHERE id = ?",
            (str(commitment_id),),
        ).fetchone()

        return self._row_to_response(row) if row is not None else None

    def list(self, status: CommitmentStatus | None = None) -> list[CommitmentResponse]:
        """
        List commitments, optionally filtered by status.

        Args:
            status: If provided, only return commitments in that status.
                If None, return all commitments.

        Returns:
            List of CommitmentResponse, sorted by created_at descending
            (most recent first). Empty list if no matches.
        """
        if status is not None:
            rows = self._conn.execute(
                "SELECT * FROM commitments WHERE status = ? ORDER BY created_at DESC",
                (status.value,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM commitments ORDER BY created_at DESC"
            ).fetchall()

        return [self._row_to_response(row) for row in rows]

    def update(
        self,
        commitment_id: UUID,
        text: str | None = None,
        due_at: datetime | None = None,
        status: CommitmentStatus | None = None,
    ) -> CommitmentResponse | None:
        """
        Partial update of a commitment. Only non-None fields are changed.

        Args:
            commitment_id: The UUID of the commitment to update.
            text: Optional new text.
            due_at: Optional new due timestamp.
            status: Optional new status.

        Returns:
            The updated CommitmentResponse, or None if no commitment with
            that id exists.
        """
        existing = self.get(commitment_id)
        if existing is None:
            return None

        # Collect only the fields that are actually being changed.
        updates: dict[str, object] = {}
        if text is not None:
            updates["text"] = text
        if due_at is not None:
            updates["due_at"] = due_at.isoformat()
        if status is not None:
            updates["status"] = status.value

        if not updates:
            # Nothing to change; return existing as-is.
            return existing

        updates["updated_at"] = datetime.now(UTC).isoformat()

        # Build SET clause dynamically — only update fields the caller provided.
        set_clause = ", ".join(f"{key} = ?" for key in updates)
        values = list(updates.values()) + [str(commitment_id)]

        self._conn.execute(
            f"UPDATE commitments SET {set_clause} WHERE id = ?",
            values,
        )
        self._conn.commit()

        return self.get(commitment_id)

    def delete(self, commitment_id: UUID) -> bool:
        """
        Hard-delete a commitment by id.

        Args:
            commitment_id: The UUID of the commitment to delete.

        Returns:
            True if a row was deleted, False if no commitment with that
            id existed.
        """
        cursor = self._conn.execute(
            "DELETE FROM commitments WHERE id = ?",
            (str(commitment_id),),
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
