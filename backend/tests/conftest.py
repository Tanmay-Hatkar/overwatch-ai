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

Schema setup uses the real migration runner (app.migrations.run_migrations)
so tests exercise the same SQL that production runs. Drift between test
fixture SQL and production schema is impossible by construction.
"""

import sqlite3
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.migrations import run_migrations
from app.models.user import UserResponse
from app.repositories.commitment_repository import CommitmentRepository
from app.repositories.user_repository import UserRepository
from app.services.commitment_service import CommitmentService
from app.services.jwt_service import issue_session_token


def _create_tables(conn: sqlite3.Connection) -> None:
    """Apply all migrations to a fresh test connection."""
    run_migrations(conn)


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
def test_user(db_connection: sqlite3.Connection) -> UserResponse:
    """
    A persisted user row. Use its `.id` to scope service/repository calls,
    or pair with `authed_client` for route tests.
    """
    return UserRepository(db_connection).create(
        google_id="g-test", email="test@example.com", name="Test User", picture=None
    )


@pytest.fixture
def authed_client(
    db_connection: sqlite3.Connection, test_user: UserResponse
) -> Generator[TestClient, None, None]:
    """
    A TestClient carrying a valid session cookie for `test_user`, so it can
    hit the auth-gated routes. Same get_db override as `client`.
    """

    def _override_get_db() -> Generator[sqlite3.Connection, None, None]:
        yield db_connection

    app.dependency_overrides[get_db] = _override_get_db
    client = TestClient(app)
    client.cookies.set("ow_session", issue_session_token(test_user.id))
    yield client
    app.dependency_overrides.clear()


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
