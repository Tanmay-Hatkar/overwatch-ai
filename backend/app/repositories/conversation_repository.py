"""
conversation_repository.py — Data access for per-user chat history.

Persists conversation turns so a user's chat context lives server-side
(survives device switches + cleared browsers) instead of only in
localStorage. The chat service appends each turn and loads the recent
tail to build prompt context.

All methods are scoped by user_id — one user can never read another's
conversation.
"""

import sqlite3
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.models.chat import ChatTurn


class ConversationRepository:
    """Data access for the conversation_turns table (scoped by user_id)."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def append(self, user_id: UUID, role: str, content: str) -> None:
        """
        Append one turn (a single user or assistant message).

        Args:
            user_id: Owner of the conversation.
            role: 'user' or 'assistant'.
            content: The message text.
        """
        self._conn.execute(
            """
            INSERT INTO conversation_turns (id, user_id, role, content, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (str(uuid4()), str(user_id), role, content, datetime.now(UTC).isoformat()),
        )
        self._conn.commit()

    def recent(self, user_id: UUID, limit: int = 10) -> list[ChatTurn]:
        """
        Return the user's most recent `limit` turns in chronological order
        (oldest first), ready to feed the prompt as conversation context.

        We select the newest `limit` by insertion order (rowid is monotonic,
        so it's a stable tiebreaker even within the same timestamp), then
        reverse to chronological order.
        """
        rows = self._conn.execute(
            """
            SELECT role, content FROM (
                SELECT role, content, rowid
                  FROM conversation_turns
                 WHERE user_id = ?
                 ORDER BY rowid DESC
                 LIMIT ?
            ) ORDER BY rowid ASC
            """,
            (str(user_id), limit),
        ).fetchall()
        return [ChatTurn(role=row["role"], content=row["content"]) for row in rows]

    def clear(self, user_id: UUID) -> int:
        """
        Delete all of a user's conversation turns. Returns the number removed.
        """
        cursor = self._conn.execute(
            "DELETE FROM conversation_turns WHERE user_id = ?",
            (str(user_id),),
        )
        self._conn.commit()
        return cursor.rowcount
