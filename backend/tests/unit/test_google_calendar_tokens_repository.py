"""
test_google_calendar_tokens_repository.py — Unit tests for the per-user
Google Calendar token store.
"""

from uuid import uuid4

from app.repositories.google_calendar_tokens_repository import (
    GoogleCalendarTokensRepository,
)
from app.repositories.user_repository import UserRepository


def _make_user(db_connection):
    """Create a user row (the tokens table has a FK to users)."""
    return UserRepository(db_connection).create("g", "t@example.com", "T", None)


def test_get_returns_none_when_absent(db_connection) -> None:
    repo = GoogleCalendarTokensRepository(db_connection)
    assert repo.get(uuid4()) is None


def test_upsert_then_get_roundtrip(db_connection) -> None:
    user = _make_user(db_connection)
    repo = GoogleCalendarTokensRepository(db_connection)
    repo.upsert(
        user.id,
        access_token="at-1",
        refresh_token="rt-1",
        token_uri="https://oauth2.googleapis.com/token",
        client_id="cid",
        client_secret="secret",
        scopes="https://www.googleapis.com/auth/calendar.readonly",
        expiry="2026-06-07T20:00:00+00:00",
    )
    row = repo.get(user.id)
    assert row is not None
    assert row["access_token"] == "at-1"
    assert row["refresh_token"] == "rt-1"
    assert row["client_id"] == "cid"


def test_upsert_updates_access_token_but_keeps_refresh_token(db_connection) -> None:
    """A refresh that omits refresh_token must not clobber the stored one."""
    user = _make_user(db_connection)
    repo = GoogleCalendarTokensRepository(db_connection)
    repo.upsert(
        user.id,
        access_token="at-1",
        refresh_token="rt-original",
        token_uri="uri",
        client_id="cid",
        client_secret="secret",
        scopes="scope",
        expiry=None,
    )
    # Simulate a refresh: new access token, no new refresh token.
    repo.upsert(
        user.id,
        access_token="at-2",
        refresh_token=None,
        token_uri="uri",
        client_id="cid",
        client_secret="secret",
        scopes="scope",
        expiry=None,
    )
    row = repo.get(user.id)
    assert row["access_token"] == "at-2"
    assert row["refresh_token"] == "rt-original"  # preserved


def test_delete_removes_row(db_connection) -> None:
    user = _make_user(db_connection)
    repo = GoogleCalendarTokensRepository(db_connection)
    repo.upsert(
        user.id,
        access_token="at",
        refresh_token="rt",
        token_uri="uri",
        client_id="cid",
        client_secret="secret",
        scopes="scope",
        expiry=None,
    )
    assert repo.delete(user.id) is True
    assert repo.get(user.id) is None
    # Idempotent — second delete reports nothing removed.
    assert repo.delete(user.id) is False
