"""
database.py — SQLite connection and schema management.

For slice 1 we use SQLite for simplicity. Switching to Postgres later
will mean changing this file (and adding migrations) — not changes
scattered throughout the codebase. That's the value of the layered
architecture.

The database file lives at backend/data/overwatch.db. The parent folder
is created automatically on first connection. The file itself is
gitignored.
"""

import sqlite3
from collections.abc import Generator
from pathlib import Path

# DB lives in backend/data/overwatch.db
_DB_PATH = Path(__file__).parent.parent / "data" / "overwatch.db"


def get_connection() -> sqlite3.Connection:
    """
    Open a new SQLite connection.

    Each call returns a NEW connection — appropriate for FastAPI's per-request
    dependency injection model. Caller is responsible for closing it.

    Returns:
        An open sqlite3.Connection with row_factory set to sqlite3.Row
        (so rows behave like dicts: row["column_name"]).
    """
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """
    Create the commitments and briefings tables if they don't exist.

    Idempotent — safe to call on every app startup. Real schema migrations
    will come later (Alembic) when the schema starts evolving in production.
    """
    conn = get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS commitments (
                id          TEXT PRIMARY KEY,
                text        TEXT NOT NULL,
                due_at      TEXT,
                status      TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS briefings (
                id            TEXT PRIMARY KEY,
                date          TEXT NOT NULL UNIQUE,
                content       TEXT NOT NULL,
                today_count   INTEGER NOT NULL,
                overdue_count INTEGER NOT NULL,
                generated_at  TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS push_subscriptions (
                id          TEXT PRIMARY KEY,
                endpoint    TEXT NOT NULL UNIQUE,
                p256dh      TEXT NOT NULL,
                auth        TEXT NOT NULL,
                created_at  TEXT NOT NULL
            )
        """)
        conn.commit()
    finally:
        conn.close()


def get_db() -> Generator[sqlite3.Connection, None, None]:
    """
    FastAPI dependency that yields a database connection per request.

    Use in routes via `conn = Depends(get_db)`. The connection is
    automatically closed when the request completes.

    Yields:
        An open sqlite3.Connection for the lifetime of one request.
    """
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()
