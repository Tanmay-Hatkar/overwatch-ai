"""
user_repository.py — Data access for the User entity.

Owns all SQL for users. As with other repositories, no business logic
lives here — services own decisions like "should we create a new user
on first sign-in?" The repository just reads and writes rows.
"""

import sqlite3
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.models.user import UserResponse


class UserRepository:
    """
    Data access class for User records.

    Construct with an open SQLite connection. The repository does not
    manage the connection lifecycle (caller owns it).
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        """
        Args:
            conn: An open SQLite connection.
        """
        self._conn = conn

    def get_by_google_id(self, google_id: str) -> UserResponse | None:
        """
        Look up a user by their immutable Google "sub" claim.

        This is the primary lookup during sign-in: every time a user
        comes back, we look them up by google_id, not by email (which
        can change).

        Args:
            google_id: The "sub" claim from a verified Google id_token.

        Returns:
            UserResponse if found, else None.
        """
        row = self._conn.execute(
            "SELECT * FROM users WHERE google_id = ?",
            (google_id,),
        ).fetchone()
        return self._row_to_response(row) if row is not None else None

    def get_by_id(self, user_id: UUID) -> UserResponse | None:
        """
        Look up a user by their internal UUID.

        Used by the `current_user` dependency to materialize the user
        from the JWT's `sub` claim (which holds our UUID, not Google's).

        Args:
            user_id: Internal UUID.

        Returns:
            UserResponse if found, else None (e.g. if the user was deleted).
        """
        row = self._conn.execute(
            "SELECT * FROM users WHERE id = ?",
            (str(user_id),),
        ).fetchone()
        return self._row_to_response(row) if row is not None else None

    def list_all_ids(self) -> list[UUID]:
        """
        Return every user's id. Used by the ReminderScheduler to iterate
        users and push each their own due reminders.
        """
        rows = self._conn.execute("SELECT id FROM users").fetchall()
        return [UUID(row["id"]) for row in rows]

    def create(
        self,
        google_id: str,
        email: str,
        name: str,
        picture: str | None,
    ) -> UserResponse:
        """
        Insert a new user row. Called the first time someone signs in.

        Args:
            google_id: Verified Google "sub" claim.
            email: User's email from the id_token.
            name: Display name from Google profile.
            picture: Optional profile picture URL.

        Returns:
            The newly created UserResponse.
        """
        new_id = str(uuid4())
        now = datetime.now(UTC).isoformat()
        self._conn.execute(
            """
            INSERT INTO users (id, google_id, email, name, picture, created_at, last_login_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (new_id, google_id, email, name, picture, now, now),
        )
        self._conn.commit()

        result = self.get_by_id(UUID(new_id))
        assert result is not None, "Just-inserted user unexpectedly missing"
        return result

    def update_last_login(self, user_id: UUID) -> None:
        """
        Bump the last_login_at timestamp to now.

        Called by /auth/me on each successful auth check (idempotent;
        we only care about the most recent value).
        """
        now = datetime.now(UTC).isoformat()
        self._conn.execute(
            "UPDATE users SET last_login_at = ? WHERE id = ?",
            (now, str(user_id)),
        )
        self._conn.commit()

    def update_profile(
        self,
        user_id: UUID,
        name: str,
        picture: str | None,
    ) -> None:
        """
        Refresh profile fields from Google on each sign-in.

        Google's id_token always carries the latest name + picture, so
        we keep our copy fresh. Email is NOT updated here — email
        changes are rare and could confuse the user; left for a
        separate explicit flow.

        Args:
            user_id: Internal UUID of the user.
            name: Current display name from Google.
            picture: Current picture URL from Google.
        """
        self._conn.execute(
            "UPDATE users SET name = ?, picture = ? WHERE id = ?",
            (name, picture, str(user_id)),
        )
        self._conn.commit()

    @staticmethod
    def _row_to_response(row: sqlite3.Row) -> UserResponse:
        """Convert a sqlite3.Row to a UserResponse."""
        return UserResponse(
            id=UUID(row["id"]),
            email=row["email"],
            name=row["name"],
            picture=row["picture"],
            created_at=datetime.fromisoformat(row["created_at"]),
            last_login_at=datetime.fromisoformat(row["last_login_at"]),
        )
