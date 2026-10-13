"""
goal_repository.py — Data access for weekly rate goals and their logs (ADR-0026).

Owns all SQL for the `goals` and `goal_logs` tables. No week arithmetic
lives here — the service decides which UTC window "this week" is and asks
for a sum over it.

Every method takes a user_id first and filters by it, same multi-tenancy
boundary as CommitmentRepository (ADR-0013).

Uses `from __future__ import annotations` because the class defines a
`list()` method that would otherwise shadow the builtin in later annotations.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from app.models.goal import GoalRecord, GoalStatus


def _ts(dt: datetime) -> str:
    """
    Render a UTC-aware instant in one fixed-width format.

    Log times are compared as strings in SQL, so every stored value and
    every window bound must share a format. isoformat() alone drops the
    microseconds when they're zero, which would make the strings uneven.
    """
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")


class GoalRepository:
    """Data access for Goal records and progress logs (scoped by user_id)."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        """
        Args:
            conn: An open SQLite connection. Caller owns its lifecycle.
        """
        self._conn = conn

    def create(self, user_id: UUID, text: str, target_count: int) -> GoalRecord:
        """
        Insert a new active goal.

        Args:
            user_id: Owner.
            text: What's being counted.
            target_count: Times per week.

        Returns:
            The created goal.
        """
        new_id = str(uuid4())
        now = datetime.now(UTC).isoformat()
        self._conn.execute(
            """
            INSERT INTO goals (id, user_id, text, target_count, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (new_id, str(user_id), text, target_count, GoalStatus.ACTIVE.value, now, now),
        )
        self._conn.commit()
        created = self.get(user_id, UUID(new_id))
        assert created is not None, "Just-inserted goal unexpectedly missing"
        return created

    def get(self, user_id: UUID, goal_id: UUID) -> GoalRecord | None:
        """Fetch one goal by id, or None if it doesn't exist for this user."""
        row = self._conn.execute(
            "SELECT * FROM goals WHERE id = ? AND user_id = ?",
            (str(goal_id), str(user_id)),
        ).fetchone()
        return self._row_to_record(row) if row is not None else None

    def list(self, user_id: UUID, status: GoalStatus | None = GoalStatus.ACTIVE) -> list[GoalRecord]:
        """
        List a user's goals, oldest first (a stable order for the home screen).

        Args:
            user_id: Owner.
            status: Filter; None returns every status.
        """
        if status is None:
            rows = self._conn.execute(
                "SELECT * FROM goals WHERE user_id = ? ORDER BY created_at ASC",
                (str(user_id),),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM goals WHERE user_id = ? AND status = ? ORDER BY created_at ASC",
                (str(user_id), status.value),
            ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def update(
        self,
        user_id: UUID,
        goal_id: UUID,
        text: str | None = None,
        target_count: int | None = None,
        status: GoalStatus | None = None,
    ) -> GoalRecord | None:
        """
        Partially update a goal. None means "leave unchanged".

        Returns:
            The updated goal, or None if it doesn't exist for this user.
        """
        updates: dict[str, object] = {}
        if text is not None:
            updates["text"] = text
        if target_count is not None:
            updates["target_count"] = target_count
        if status is not None:
            updates["status"] = status.value
        return self._apply_updates(user_id, goal_id, updates)

    def set_week_decision(
        self, user_id: UUID, goal_id: UUID, decision: str | None, week_start: date
    ) -> GoalRecord | None:
        """Record the check-in answer for `week_start` (None clears it)."""
        updates = {
            "decision": decision,
            "decision_week": week_start.isoformat() if decision is not None else None,
        }
        return self._apply_updates(user_id, goal_id, updates)

    def delete(self, user_id: UUID, goal_id: UUID) -> bool:
        """Hard-delete a goal (its logs cascade). Returns True if a row went."""
        # Logs are deleted explicitly too: ON DELETE CASCADE only fires when
        # the connection has PRAGMA foreign_keys on, which test connections
        # don't set.
        self._conn.execute(
            "DELETE FROM goal_logs WHERE goal_id = ? AND user_id = ?",
            (str(goal_id), str(user_id)),
        )
        cursor = self._conn.execute(
            "DELETE FROM goals WHERE id = ? AND user_id = ?",
            (str(goal_id), str(user_id)),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def add_log(self, user_id: UUID, goal_id: UUID, amount: int, logged_at: datetime) -> None:
        """Record `amount` units of progress at `logged_at` (UTC-aware)."""
        self._conn.execute(
            "INSERT INTO goal_logs (id, goal_id, user_id, amount, logged_at) VALUES (?, ?, ?, ?, ?)",
            (str(uuid4()), str(goal_id), str(user_id), amount, _ts(logged_at)),
        )
        self._touch(user_id, goal_id)

    def delete_latest_log(
        self, user_id: UUID, goal_id: UUID, since: datetime, until: datetime
    ) -> bool:
        """
        Remove the most recent log inside [since, until). Used for undo.

        Returns:
            True if a log was removed, False if there was none in the window.
        """
        row = self._conn.execute(
            """
            SELECT id FROM goal_logs
             WHERE goal_id = ? AND user_id = ? AND logged_at >= ? AND logged_at < ?
             ORDER BY logged_at DESC LIMIT 1
            """,
            (str(goal_id), str(user_id), _ts(since), _ts(until)),
        ).fetchone()
        if row is None:
            return False
        self._conn.execute("DELETE FROM goal_logs WHERE id = ?", (row["id"],))
        self._touch(user_id, goal_id)
        return True

    def sum_logs(self, user_id: UUID, goal_id: UUID, since: datetime, until: datetime) -> int:
        """Total logged amount inside [since, until)."""
        row = self._conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS total FROM goal_logs
             WHERE goal_id = ? AND user_id = ? AND logged_at >= ? AND logged_at < ?
            """,
            (str(goal_id), str(user_id), _ts(since), _ts(until)),
        ).fetchone()
        return int(row["total"])

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _apply_updates(
        self, user_id: UUID, goal_id: UUID, updates: dict[str, object]
    ) -> GoalRecord | None:
        """Write `updates` (column -> value) plus updated_at; return the fresh row."""
        existing = self.get(user_id, goal_id)
        if existing is None:
            return None
        if not updates:
            return existing
        updates = {**updates, "updated_at": datetime.now(UTC).isoformat()}
        set_clause = ", ".join(f"{key} = ?" for key in updates)
        self._conn.execute(
            f"UPDATE goals SET {set_clause} WHERE id = ? AND user_id = ?",
            [*updates.values(), str(goal_id), str(user_id)],
        )
        self._conn.commit()
        return self.get(user_id, goal_id)

    def _touch(self, user_id: UUID, goal_id: UUID) -> None:
        """Bump updated_at (and commit) after a log change."""
        self._conn.execute(
            "UPDATE goals SET updated_at = ? WHERE id = ? AND user_id = ?",
            (datetime.now(UTC).isoformat(), str(goal_id), str(user_id)),
        )
        self._conn.commit()

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> GoalRecord:
        """Convert a goals row into a GoalRecord."""
        return GoalRecord(
            id=UUID(row["id"]),
            text=row["text"],
            target_count=row["target_count"],
            status=GoalStatus(row["status"]),
            decision=row["decision"],
            decision_week=date.fromisoformat(row["decision_week"]) if row["decision_week"] else None,
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
