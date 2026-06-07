"""
google_calendar_tokens_repository.py — Data access for stored Google
Calendar OAuth credentials.

One row per user (PRIMARY KEY user_id). Holds everything
google.oauth2.credentials.Credentials needs to reconstruct itself and
self-refresh: access/refresh tokens, token URI, client id/secret, scopes,
expiry.

No business logic here — just reads, writes, and row⇄dict conversion.
"""

import sqlite3
from datetime import UTC, datetime
from uuid import UUID


class GoogleCalendarTokensRepository:
    """Data access for the google_calendar_tokens table."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        """
        Args:
            conn: An open SQLite connection. The repository does NOT manage
                the connection lifecycle (caller owns it).
        """
        self._conn = conn

    def get(self, user_id: UUID) -> dict | None:
        """
        Return the stored token row for a user as a dict, or None.

        Args:
            user_id: Owner of the calendar connection.

        Returns:
            A dict with keys matching the table columns, or None if the
            user has not connected their calendar.
        """
        row = self._conn.execute(
            "SELECT * FROM google_calendar_tokens WHERE user_id = ?",
            (str(user_id),),
        ).fetchone()
        return dict(row) if row is not None else None

    def upsert(
        self,
        user_id: UUID,
        *,
        access_token: str,
        refresh_token: str | None,
        token_uri: str,
        client_id: str,
        client_secret: str,
        scopes: str,
        expiry: str | None,
    ) -> None:
        """
        Insert or update a user's calendar token row.

        On conflict (user already connected), every field except
        created_at is overwritten. refresh_token is only overwritten when
        a new one is supplied — Google omits it on re-consent sometimes,
        and we must not clobber a good refresh token with NULL.

        Args:
            user_id: Owner of the connection.
            access_token: Short-lived OAuth access token.
            refresh_token: Long-lived refresh token (may be None on refresh).
            token_uri: Google's token endpoint.
            client_id: OAuth client id used.
            client_secret: OAuth client secret used.
            scopes: Space-separated granted scopes.
            expiry: ISO 8601 expiry of the access token, or None.
        """
        now = datetime.now(UTC).isoformat()
        self._conn.execute(
            """
            INSERT INTO google_calendar_tokens (
                user_id, access_token, refresh_token, token_uri,
                client_id, client_secret, scopes, expiry,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                access_token  = excluded.access_token,
                refresh_token = COALESCE(excluded.refresh_token, google_calendar_tokens.refresh_token),
                token_uri     = excluded.token_uri,
                client_id     = excluded.client_id,
                client_secret = excluded.client_secret,
                scopes        = excluded.scopes,
                expiry        = excluded.expiry,
                updated_at    = excluded.updated_at
            """,
            (
                str(user_id),
                access_token,
                refresh_token,
                token_uri,
                client_id,
                client_secret,
                scopes,
                expiry,
                now,
                now,
            ),
        )
        self._conn.commit()

    def delete(self, user_id: UUID) -> bool:
        """
        Remove a user's stored calendar token (disconnect).

        Args:
            user_id: Owner of the connection.

        Returns:
            True if a row was deleted, False if there was nothing stored.
        """
        cursor = self._conn.execute(
            "DELETE FROM google_calendar_tokens WHERE user_id = ?",
            (str(user_id),),
        )
        self._conn.commit()
        return cursor.rowcount > 0
