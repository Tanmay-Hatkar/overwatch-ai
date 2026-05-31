"""
briefing_repository.py — Data access for cached Briefings.

One row per date (UNIQUE constraint on `date` column). Upserts on save
so writing twice for the same date overwrites instead of erroring.
"""

import sqlite3
from datetime import date, datetime
from uuid import uuid4

from app.models.briefing import BriefingResponse


class BriefingRepository:
    """
    Data access class for cached briefings.

    Construct with an open SQLite connection. The repo doesn't manage the
    connection lifecycle (caller owns it).
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get_for_date(self, day: date) -> BriefingResponse | None:
        """
        Return the cached briefing for the given date, or None if absent.

        Any returned briefing is marked `cached=True` — it came from storage.
        """
        row = self._conn.execute(
            "SELECT * FROM briefings WHERE date = ?",
            (day.isoformat(),),
        ).fetchone()
        return self._row_to_response(row) if row is not None else None

    def save(self, briefing: BriefingResponse, day: date) -> BriefingResponse:
        """
        Upsert a briefing for the given date.

        If a row already exists for that date, replace it. The `cached`
        field on the returned briefing is True (next call to get_for_date
        will return this row).
        """
        self._conn.execute(
            """
            INSERT INTO briefings (id, date, content, today_count, overdue_count, generated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                content       = excluded.content,
                today_count   = excluded.today_count,
                overdue_count = excluded.overdue_count,
                generated_at  = excluded.generated_at
            """,
            (
                str(uuid4()),
                day.isoformat(),
                briefing.content,
                briefing.today_count,
                briefing.overdue_count,
                briefing.generated_at.isoformat(),
            ),
        )
        self._conn.commit()
        result = self.get_for_date(day)
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
