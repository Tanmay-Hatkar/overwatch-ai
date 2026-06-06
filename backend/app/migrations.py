"""
migrations.py — Hand-rolled SQL migration runner.

Why hand-rolled instead of Alembic:
  - We're small (10ish tables max for the foreseeable future)
  - Plain SQL files are dead simple to review
  - Alembic adds a config file, env.py, autogenerate quirks, and a
    learning curve we don't need yet

Replacing this with Alembic later is straightforward — the migration
files become alembic revisions and the `schema_migrations` table
becomes alembic's `alembic_version`.

How it works:
  - Migration files live in backend/migrations/ as NNN_<description>.sql
  - On startup, init_db() scans the folder in lexical order
  - Each unapplied migration runs in a single transaction
  - The schema_migrations table records (version, applied_at)
  - Idempotent — running twice is a no-op
"""

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

_MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"


def _ensure_migrations_table(conn: sqlite3.Connection) -> None:
    """
    Create the schema_migrations bookkeeping table if it doesn't exist.

    One row per applied migration. Lookup happens once at startup, so
    no index is needed beyond the primary key.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version    TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    conn.commit()


def _applied_versions(conn: sqlite3.Connection) -> set[str]:
    """
    Return the set of migration versions already applied.

    Args:
        conn: An open SQLite connection.

    Returns:
        A set of version strings (e.g. {"001", "002"}).
    """
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {row[0] for row in rows}


def _discover_migrations() -> list[tuple[str, Path]]:
    """
    Scan the migrations/ folder for SQL files in lexical order.

    A migration file is named NNN_description.sql where NNN is a
    zero-padded numeric prefix. The prefix is the "version" stored in
    schema_migrations.

    Returns:
        List of (version, path) tuples sorted by version.

    Raises:
        ValueError: If the migrations folder doesn't exist or a file
            doesn't match the expected naming pattern.
    """
    if not _MIGRATIONS_DIR.exists():
        raise ValueError(f"Migrations directory not found: {_MIGRATIONS_DIR}")

    discovered: list[tuple[str, Path]] = []
    for path in sorted(_MIGRATIONS_DIR.glob("*.sql")):
        # Filename pattern: NNN_description.sql
        prefix = path.stem.split("_", 1)[0]
        if not prefix.isdigit():
            raise ValueError(
                f"Migration filename must start with a numeric prefix: {path.name}"
            )
        discovered.append((prefix, path))
    return discovered


def run_migrations(conn: sqlite3.Connection) -> list[str]:
    """
    Apply any unapplied migrations to the database in order.

    Each migration runs in a transaction — if it fails, the database
    rolls back and the version is NOT recorded, so a re-run will try
    again. Migrations after a failed one do NOT run.

    Args:
        conn: An open SQLite connection.

    Returns:
        List of version strings that were applied in this call. Empty
        list means the database was already up to date.

    Raises:
        sqlite3.DatabaseError: If a migration SQL file fails to execute.
    """
    _ensure_migrations_table(conn)
    applied = _applied_versions(conn)
    pending = [(v, p) for v, p in _discover_migrations() if v not in applied]

    if not pending:
        logger.debug("No pending migrations")
        return []

    applied_now: list[str] = []
    for version, path in pending:
        logger.info("Applying migration %s (%s)", version, path.name)
        sql = path.read_text(encoding="utf-8")
        try:
            # executescript runs multiple statements; auto-commits on success.
            # We wrap in an explicit transaction so we can rollback on error.
            conn.execute("BEGIN")
            conn.executescript(sql)
            from datetime import UTC, datetime

            now = datetime.now(UTC).isoformat()
            conn.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (version, now),
            )
            conn.commit()
            applied_now.append(version)
            logger.info("Migration %s applied successfully", version)
        except sqlite3.DatabaseError:
            conn.rollback()
            logger.exception("Migration %s FAILED — rolled back", version)
            raise

    return applied_now
