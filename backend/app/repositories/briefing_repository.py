"""
briefing_repository.py — Data access for cached Briefings.

One row per (user_id, date) — the composite uniqueness enforced by the
schema (migration 004). Upserts on save so writing twice for the same
user+date overwrites instead of erroring.
"""

import sqlite3
from datetime import date, datetime
from uuid import UUID, uuid4

from app.models.briefing import BriefingResponse


class BriefingRepository:
    """Data access for cached briefings (scoped by user_id)."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get_for_date(self, user_id: UUID, day: date) -> BriefingResponse | None:
        """Return this user's cached briefing for the date, or None."""
        row = self._conn.execute(
            "SELECT * FROM briefings WHERE user_id = ? AND date = ?",
            (str(user_id), day.isoformat()),
        ).fetchone()
        return self._row_to_response(row) if row is not None else None

    def save(
        self, user_id: UUID, briefing: BriefingResponse, day: date
    ) -> BriefingResponse:
        """Upsert a briefing for this user + date."""
        self._conn.execute(
            """
            INSERT INTO briefings (id, user_id, date, content, today_count, overdue_count, generated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, date) DO UPDATE SET
                content       = excluded.content,
                today_count   = excluded.today_count,
                overdue_count = excluded.overdue_count,
                generated_at  = excluded.generated_at
            """,
            (
                str(uuid4()),
                str(user_id),
                day.isoformat(),
                briefing.content,
                briefing.today_count,
                briefing.overdue_count,
                briefing.generated_at.isoformat(),
            ),
        )
        self._conn.commit()
        result = self.get_for_date(user_id, day)
        assert result is not None, "Just-upserted briefing unexpectedly missing"
        return result

    @staticmethod
    def _row_to_response(row: sqlite3.Row) -> BriefingResponse:
        """Convert a sqlite3.Row to a BriefingResponse. Always cached=True."""
        return BriefingResponse(
            content=row["content"],
            today_count=row["today_count"],
            overdue_count=row["overdue_count"],
            generated_at=datetime.fromisoformat(row["generated_at"]),
            cached=True,
        )
