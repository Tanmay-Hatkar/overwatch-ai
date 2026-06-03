"""
push_subscription_repository.py — Data access for Web Push subscriptions.

One row per browser/device. Endpoint is unique — re-subscribing from the
same browser replaces the previous record (upsert by endpoint).
"""

import sqlite3
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.models.push import PushSubscriptionResponse


class PushSubscriptionRepository:
    """Stores and fetches Web Push subscriptions."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def upsert(self, endpoint: str, p256dh: str, auth: str) -> PushSubscriptionResponse:
        """
        Insert a subscription, or replace the existing row for this endpoint.

        Returns the persisted record (including server-assigned id + created_at).
        """
        existing = self._fetch_by_endpoint(endpoint)
        if existing is not None:
            # Refresh the keys in case the browser rotated them
            self._conn.execute(
                "UPDATE push_subscriptions SET p256dh = ?, auth = ? WHERE endpoint = ?",
                (p256dh, auth, endpoint),
            )
            self._conn.commit()
            updated = self._fetch_by_endpoint(endpoint)
            assert updated is not None
            return updated

        new_id = str(uuid4())
        now = datetime.now(UTC).isoformat()
        self._conn.execute(
            """
            INSERT INTO push_subscriptions (id, endpoint, p256dh, auth, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (new_id, endpoint, p256dh, auth, now),
        )
        self._conn.commit()
        fetched = self._fetch_by_endpoint(endpoint)
        assert fetched is not None
        return fetched

    def delete_by_endpoint(self, endpoint: str) -> bool:
        """Remove the subscription for this endpoint. Returns True if a row was deleted."""
        cursor = self._conn.execute(
            "DELETE FROM push_subscriptions WHERE endpoint = ?",
            (endpoint,),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def list_all(self) -> list[PushSubscriptionResponse]:
        """Return all subscriptions — used by the scheduler to broadcast pushes."""
        rows = self._conn.execute(
            "SELECT * FROM push_subscriptions ORDER BY created_at"
        ).fetchall()
        return [self._row_to_response(r) for r in rows]

    # ------------------------------------------------------------------

    def _fetch_by_endpoint(self, endpoint: str) -> PushSubscriptionResponse | None:
        row = self._conn.execute(
            "SELECT * FROM push_subscriptions WHERE endpoint = ?",
            (endpoint,),
        ).fetchone()
        return self._row_to_response(row) if row is not None else None

    @staticmethod
    def _row_to_response(row: sqlite3.Row) -> PushSubscriptionResponse:
        return PushSubscriptionResponse(
            id=UUID(row["id"]),
            endpoint=row["endpoint"],
            p256dh=row["p256dh"],
            auth=row["auth"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
