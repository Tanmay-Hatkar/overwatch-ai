"""
reflection_repository.py — Data access for cached evening Reflections.

One row per (user_id, date) — the composite uniqueness enforced by the
schema (migration 010). Upserts on save so writing twice for the same
user+date overwrites instead of erroring. Mirrors briefing_repository.py.
"""

import sqlite3
from datetime import date, datetime
from uuid import UUID, uuid4

from app.models.reflection import ReflectionResponse


class ReflectionRepository:
    """Data access for cached evening reflections (scoped by user_id)."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get_for_date(self, user_id: UUID, day: date) -> ReflectionResponse | None:
        """Return this user's cached reflection for the date, or None."""
        row = self._conn.execute(
            "SELECT * FROM reflections WHERE user_id = ? AND date = ?",
            (str(user_id), day.isoformat()),
        ).fetchone()
        return self._row_to_response(row) if row is not None else None

    def save(
        self, user_id: UUID, reflection: ReflectionResponse, day: date
    ) -> ReflectionResponse:
        """Upsert a reflection for this user + date."""
        self._conn.execute(
            """
            INSERT INTO reflections
                (id, user_id, date, content, done_count, open_count, abandoned_count, generated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, date) DO UPDATE SET
                content         = excluded.content,
                done_count      = excluded.done_count,
                open_count      = excluded.open_count,
                abandoned_count = excluded.abandoned_count,
                generated_at    = excluded.generated_at
            """,
            (
                str(uuid4()),
                str(user_id),
                day.isoformat(),
                reflection.content,
                reflection.done_count,
                reflection.open_count,
                reflection.abandoned_count,
                reflection.generated_at.isoformat(),
            ),
        )
        self._conn.commit()
        result = self.get_for_date(user_id, day)
        assert result is not None, "Just-upserted reflection unexpectedly missing"
        return result

    @staticmethod
    def _row_to_response(row: sqlite3.Row) -> ReflectionResponse:
        """Convert a sqlite3.Row to a ReflectionResponse. Always cached=True."""
        return ReflectionResponse(
            content=row["content"],
            done_count=row["done_count"],
            open_count=row["open_count"],
            abandoned_count=row["abandoned_count"],
            generated_at=datetime.fromisoformat(row["generated_at"]),
            cached=True,
        )
