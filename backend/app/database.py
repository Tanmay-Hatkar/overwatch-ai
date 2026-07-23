"""
database.py — SQLite connection and schema management.

Schema lives in the migrations/ folder as numbered SQL files. On startup
init_db() applies any unapplied migrations (see app.migrations).

For slice 1 we use SQLite for simplicity. Switching to Postgres later
will mean changing this file (and adapting the migration files) — not
changes scattered throughout the codebase. That's the value of the
layered architecture.

The database file lives at backend/data/overwatch.db. The parent folder
is created automatically on first connection. The file itself is
gitignored.
"""

import sqlite3
from collections.abc import Generator
from pathlib import Path

from app.config import settings
from app.migrations import run_migrations

# Default location: backend/data/overwatch.db (relative to this file).
# Production override via settings.database_path env var (e.g. Railway
# volume at /data/overwatch.db) so the DB survives container restarts.
_DEFAULT_DB_PATH = Path(__file__).parent.parent / "data" / "overwatch.db"


def _resolve_db_path() -> Path:
    """Return settings.database_path if set, otherwise the default dev path."""
    return Path(settings.database_path) if settings.database_path else _DEFAULT_DB_PATH


def get_connection() -> sqlite3.Connection:
    """
    Open a new SQLite connection.

    Each call returns a NEW connection — appropriate for FastAPI's per-request
    dependency injection model. Caller is responsible for closing it.

    Returns:
        An open sqlite3.Connection with row_factory set to sqlite3.Row
        (so rows behave like dicts: row["column_name"]).
    """
    db_path = _resolve_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # timeout: if the database is locked, wait up to 15s for it to free up
    # before raising — the Python-driver-level companion to PRAGMA busy_timeout.
    #
    # check_same_thread=False: FastAPI runs sync path operations and their
    # `yield`-based dependencies via anyio's worker threadpool, which does
    # not guarantee a get_db() generator's setup and its post-request
    # conn.close() teardown land on the same OS thread under concurrent
    # load (e.g. the ~6 parallel requests the frontend fires on page
    # load). Without this flag, that thread hop raises
    # "SQLite objects created in a thread can only be used in that same
    # thread" and 500s the request. Safe here because each connection is
    # still only ever used sequentially within one logical request/tick —
    # never concurrently from two threads at once.
    conn = sqlite3.connect(db_path, timeout=15.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row

    # Concurrency hardening. The frontend fires ~6 requests in parallel on
    # page load, and the reminder scheduler polls in the background — all
    # against one SQLite file. Without these, colliding connections fail
    # instantly with "database is locked", causing intermittent load errors
    # that clear on refresh. With them, reads and a writer run concurrently
    # and any lock is waited out rather than failing.
    conn.execute("PRAGMA journal_mode = WAL")   # readers + 1 writer, no mutual block
    conn.execute("PRAGMA busy_timeout = 15000")  # wait up to 15s for a lock
    conn.execute("PRAGMA synchronous = NORMAL")  # safe + faster under WAL
    # Enforce foreign keys (off by default in SQLite for legacy reasons)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """
    Apply all pending schema migrations.

    Idempotent — safe to call on every app startup. Migration tracking
    lives in the schema_migrations table.

    Raises:
        sqlite3.DatabaseError: If a migration fails. The database stays
            in its prior state because each migration runs in a
            transaction.
    """
    conn = get_connection()
    try:
        run_migrations(conn)
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
