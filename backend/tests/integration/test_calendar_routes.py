"""
test_calendar_routes.py — Integration tests for /calendar endpoints.

The test client hits the routes which use the module-level MockCalendarProvider
(no provider override needed). Verifies the endpoint contract.
"""

from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient


def _next_weekday() -> bool:
    """Return True if the next weekday is reachable (always True)."""
    return True


def test_today_returns_list(client: TestClient) -> None:
    """GET /calendar/today returns a JSON array (possibly empty)."""
    response = client.get("/calendar/today")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_today_event_shape(client: TestClient) -> None:
    """If today has events, each item has the expected fields."""
    response = client.get("/calendar/today")
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


def test_week_returns_list(client: TestClient) -> None:
    """GET /calendar/week returns a JSON array."""
    response = client.get("/calendar/week")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_week_events_are_sorted_by_start(client: TestClient) -> None:
    """Events come back sorted by start_at."""
    response = client.get("/calendar/week")
    events = response.json()
    starts = [datetime.fromisoformat(e["start_at"]) for e in events]
    assert starts == sorted(starts)


def test_week_events_within_current_week(client: TestClient) -> None:
    """All week events fall within Mon..Sun of the current ISO week."""
    response = client.get("/calendar/week")
    events = response.json()

    today = datetime.now(UTC).date()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)

    for e in events:
        event_date = datetime.fromisoformat(e["start_at"]).date()
        assert monday <= event_date <= sunday, (
            f"Event {e['id']} on {event_date} outside week {monday}..{sunday}"
        )
