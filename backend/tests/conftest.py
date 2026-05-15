"""
conftest.py — Shared pytest fixtures for Overwatch backend tests.

Fixtures defined here are auto-discovered by pytest. Every test file in
the tests/ tree can use them without imports.

Strategy:
  - db_connection: a fresh in-memory SQLite database per test. No persistence,
    no test pollution between cases.
  - repo / service: the corresponding repository and service classes wired
    to the test database.
  - client: a FastAPI TestClient with the get_db dependency overridden to
    use the test database. Lets us hit real HTTP endpoints in tests.
"""

import sqlite3
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.repositories.commitment_repository import CommitmentRepository
from app.services.commitment_service import CommitmentService


def _create_tables(conn: sqlite3.Connection) -> None:
    """Create the commitments table on a fresh connection."""
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
    conn.commit()


@pytest.fixture
def db_connection() -> Generator[sqlite3.Connection, None, None]:
    """
    Fresh in-memory SQLite database for each test.

    check_same_thread=False is needed because FastAPI's TestClient runs
    route handlers in a worker thread, but the connection is created here
    in the main pytest thread. SQLite blocks cross-thread access by default
    for safety. We use it serially in tests (no real concurrency), so this
    is safe.

    Yields:
        An open sqlite3.Connection with row_factory set and tables created.
        Closed automatically when the test finishes.
    """
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    _create_tables(conn)
    yield conn
    conn.close()


@pytest.fixture
def repo(db_connection: sqlite3.Connection) -> CommitmentRepository:
    """A CommitmentRepository wired to a fresh in-memory database."""
    return CommitmentRepository(db_connection)


@pytest.fixture
def service(repo: CommitmentRepository) -> CommitmentService:
    """A CommitmentService wired to a fresh in-memory repository."""
    return CommitmentService(repo)


@pytest.fixture
def client(db_connection: sqlite3.Connection) -> Generator[TestClient, None, None]:
    """
    FastAPI TestClient with get_db overridden to use the test database.

    Standard FastAPI testing pattern: app.dependency_overrides lets you
    substitute any Depends() function with a test version. We swap get_db
    so routes use our in-memory test database instead of the real file.
    """

    def _override_get_db() -> Generator[sqlite3.Connection, None, None]:
        yield db_connection

    app.dependency_overrides[get_db] = _override_get_db
    yield TestClient(app)
    # Cleanup: remove the override so it doesn't leak into other tests.
    app.dependency_overrides.clear()
