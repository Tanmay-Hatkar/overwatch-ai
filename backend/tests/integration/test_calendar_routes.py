"""
test_calendar_routes.py — Integration tests for /calendar endpoints.

The /calendar display routes require authentication and build a per-user
provider. A signed-in user with no stored Google token falls back to the
MockCalendarProvider in the (default) development environment, so these
tests still see mock events.
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.repositories.user_repository import UserRepository
from app.services.jwt_service import issue_session_token


@pytest.fixture
def authed_client(client: TestClient, db_connection) -> TestClient:
    """A TestClient carrying a valid session cookie for a freshly-created user."""
    repo = UserRepository(db_connection)
    user = repo.create("g-cal", "cal@example.com", "Cal User", None)
    client.cookies.set("ow_session", issue_session_token(user.id))
    return client


def test_today_requires_auth(client: TestClient) -> None:
    """GET /calendar/today is 401 without a session."""
    assert client.get("/calendar/today").status_code == 401


def test_today_returns_list(authed_client: TestClient) -> None:
    """GET /calendar/today returns a JSON array (possibly empty)."""
    response = authed_client.get("/calendar/today")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_today_event_shape(authed_client: TestClient) -> None:
    """If today has events, each item has the expected fields."""
    response = authed_client.get("/calendar/today")
    events = response.json()
    # We may or may not have events depending on day of week — only assert
    # shape if there are any
    for e in events:
        assert "id" in e
        assert "source" in e
        assert "title" in e
        assert "start_at" in e
        assert "end_at" in e
        assert "all_day" in e


def test_week_returns_list(authed_client: TestClient) -> None:
    """GET /calendar/week returns a JSON array."""
    response = authed_client.get("/calendar/week")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_week_events_are_sorted_by_start(authed_client: TestClient) -> None:
    """Events come back sorted by start_at."""
    response = authed_client.get("/calendar/week")
    events = response.json()
    starts = [datetime.fromisoformat(e["start_at"]) for e in events]
    assert starts == sorted(starts)


def test_week_events_within_current_week(authed_client: TestClient) -> None:
    """All week events fall within Mon..Sun of the current ISO week."""
    response = authed_client.get("/calendar/week")
    events = response.json()

    today = datetime.now(UTC).date()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)

    for e in events:
        event_date = datetime.fromisoformat(e["start_at"]).date()
        assert monday <= event_date <= sunday, (
            f"Event {e['id']} on {event_date} outside week {monday}..{sunday}"
        )


def test_connection_status_false_when_not_connected(authed_client: TestClient) -> None:
    """A user who hasn't linked Google reports connected=False."""
    response = authed_client.get("/calendar/connection")
    assert response.status_code == 200
    assert response.json() == {"connected": False}


def test_connection_status_requires_auth(client: TestClient) -> None:
    """GET /calendar/connection is 401 without a session."""
    assert client.get("/calendar/connection").status_code == 401


def test_disconnect_is_idempotent(authed_client: TestClient) -> None:
    """POST /calendar/disconnect returns 204 even with nothing stored."""
    assert authed_client.post("/calendar/disconnect").status_code == 204
