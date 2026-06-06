"""
test_user_repository.py — Unit tests for UserRepository.

Covers all five public methods + the row -> response mapping.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.repositories.user_repository import UserRepository


@pytest.fixture
def user_repo(db_connection) -> UserRepository:
    """A UserRepository wired to the shared in-memory DB."""
    return UserRepository(db_connection)


def test_create_inserts_and_returns_user(user_repo: UserRepository) -> None:
    """Creating a user returns the populated record with id + timestamps."""
    user = user_repo.create(
        google_id="google-sub-1",
        email="alice@example.com",
        name="Alice",
        picture="https://example.com/alice.png",
    )
    assert user.email == "alice@example.com"
    assert user.name == "Alice"
    assert user.picture == "https://example.com/alice.png"
    assert isinstance(user.created_at, datetime)
    assert isinstance(user.last_login_at, datetime)


def test_create_persists_to_database(user_repo: UserRepository) -> None:
    """Created user is fetchable by id afterwards."""
    user = user_repo.create("g1", "bob@example.com", "Bob", None)
    fetched = user_repo.get_by_id(user.id)
    assert fetched is not None
    assert fetched.id == user.id


def test_get_by_google_id_returns_user(user_repo: UserRepository) -> None:
    """Lookup by Google sub returns the matching user."""
    user_repo.create("google-xyz", "carol@example.com", "Carol", None)
    user = user_repo.get_by_google_id("google-xyz")
    assert user is not None
    assert user.email == "carol@example.com"


def test_get_by_google_id_returns_none_when_missing(user_repo: UserRepository) -> None:
    assert user_repo.get_by_google_id("never-exists") is None


def test_get_by_id_returns_none_when_missing(user_repo: UserRepository) -> None:
    assert user_repo.get_by_id(uuid4()) is None


def test_update_last_login_advances_timestamp(user_repo: UserRepository) -> None:
    """update_last_login moves last_login_at forward in time."""
    user = user_repo.create("g2", "dave@example.com", "Dave", None)
    initial = user.last_login_at

    # Sleep would be flaky; instead, write a very-old timestamp directly,
    # then call update_last_login and assert it's recent.
    import time

    time.sleep(0.01)
    user_repo.update_last_login(user.id)

    refreshed = user_repo.get_by_id(user.id)
    assert refreshed is not None
    assert refreshed.last_login_at > initial


def test_update_profile_changes_name_and_picture(user_repo: UserRepository) -> None:
    """Name + picture can be refreshed from Google; email is not touched."""
    user = user_repo.create(
        "g3", "eve@example.com", "Eve Old", "https://example.com/old.png"
    )
    user_repo.update_profile(user.id, name="Eve New", picture="https://example.com/new.png")

    refreshed = user_repo.get_by_id(user.id)
    assert refreshed is not None
    assert refreshed.name == "Eve New"
    assert refreshed.picture == "https://example.com/new.png"
    assert refreshed.email == "eve@example.com"  # unchanged


def test_update_profile_handles_null_picture(user_repo: UserRepository) -> None:
    """Picture can be set back to None (e.g. user removed their photo)."""
    user = user_repo.create("g4", "frank@example.com", "Frank", "https://example.com/f.png")
    user_repo.update_profile(user.id, name="Frank", picture=None)

    refreshed = user_repo.get_by_id(user.id)
    assert refreshed is not None
    assert refreshed.picture is None


def test_email_is_unique(user_repo: UserRepository) -> None:
    """Two users cannot share an email (DB UNIQUE constraint)."""
    import sqlite3

    user_repo.create("g5", "shared@example.com", "User One", None)
    with pytest.raises(sqlite3.IntegrityError):
        user_repo.create("g6", "shared@example.com", "User Two", None)


def test_google_id_is_unique(user_repo: UserRepository) -> None:
    """Two users cannot share a Google sub (would mean re-creating)."""
    import sqlite3

    user_repo.create("same-google-sub", "a@example.com", "A", None)
    with pytest.raises(sqlite3.IntegrityError):
        user_repo.create("same-google-sub", "b@example.com", "B", None)
