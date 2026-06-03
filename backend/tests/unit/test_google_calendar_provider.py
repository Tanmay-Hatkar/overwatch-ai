"""
test_google_calendar_provider.py — Unit tests for GoogleCalendarProvider.

All Google API library calls are mocked at the import sites inside the
provider module. No real network or filesystem credentials are used.
"""

from datetime import UTC, date, datetime
from unittest.mock import MagicMock, patch

import pytest

from app.providers.google_calendar_provider import GoogleCalendarProvider


# Patch targets — where the provider imports each name
CREDS_TARGET = "app.providers.google_calendar_provider.Credentials"
BUILD_TARGET = "app.providers.google_calendar_provider.build"


@pytest.fixture
def provider(tmp_path):
    """A provider configured with non-existent default paths."""
    return GoogleCalendarProvider(
        credentials_file=str(tmp_path / "credentials.json"),
        token_file=str(tmp_path / "token.json"),
    )


@pytest.fixture
def configured_provider(tmp_path):
    """A provider whose credentials.json + token.json both exist (empty files)."""
    creds_path = tmp_path / "credentials.json"
    token_path = tmp_path / "token.json"
    creds_path.write_text("{}")
    token_path.write_text("{}")
    return GoogleCalendarProvider(
        credentials_file=str(creds_path),
        token_file=str(token_path),
    )


# ---------------------------------------------------------------------------
# Configuration / disabled state
# ---------------------------------------------------------------------------


def test_is_configured_false_when_files_missing(provider) -> None:
    """No credentials.json → not configured."""
    assert provider.is_configured() is False


def test_is_configured_true_when_both_files_present(configured_provider) -> None:
    """Both files present → configured."""
    assert configured_provider.is_configured() is True


def test_returns_empty_when_not_configured(provider) -> None:
    """Unconfigured provider returns [] without trying to call Google."""
    assert provider.list_events_for_date(date.today()) == []
    assert provider.list_events_for_range(date.today(), date.today()) == []


# ---------------------------------------------------------------------------
# Event mapping — timed events
# ---------------------------------------------------------------------------


def _make_timed_event(
    event_id="event-1",
    summary="Test event",
    start="2026-06-02T15:00:00+00:00",
    end="2026-06-02T16:00:00+00:00",
    **extra,
):
    """Build a Google-shaped event dict for testing."""
    return {
        "id": event_id,
        "summary": summary,
        "start": {"dateTime": start},
        "end": {"dateTime": end},
        **extra,
    }


def _run_list_events(configured_provider, items):
    """Mock the Google API stack to return `items` and call list_events_for_range."""
    fake_service = MagicMock()
    fake_service.events().list().execute.return_value = {"items": items}

    fake_creds = MagicMock()
    fake_creds.expired = False

    with patch(CREDS_TARGET) as MockCreds, patch(BUILD_TARGET, return_value=fake_service):
        MockCreds.from_authorized_user_file.return_value = fake_creds
        return configured_provider.list_events_for_range(
            date(2026, 6, 2), date(2026, 6, 2)
        )


def test_maps_timed_event_to_calendar_event(configured_provider) -> None:
    """Timed Google event becomes a non-all-day CalendarEvent."""
    items = [_make_timed_event()]
    events = _run_list_events(configured_provider, items)

    assert len(events) == 1
    e = events[0]
    assert e.id == "event-1"
    assert e.source == "google"
    assert e.title == "Test event"
    assert e.start_at == datetime(2026, 6, 2, 15, 0, tzinfo=UTC)
    assert e.end_at == datetime(2026, 6, 2, 16, 0, tzinfo=UTC)
    assert e.all_day is False


def test_uses_no_title_when_summary_missing(configured_provider) -> None:
    """An event without a summary gets a sentinel title."""
    items = [_make_timed_event(summary=None)]
    # Need to remove summary from the dict (the helper set it to None which
    # is truthy as a key). Construct directly:
    raw = {
        "id": "x",
        "start": {"dateTime": "2026-06-02T15:00:00+00:00"},
        "end": {"dateTime": "2026-06-02T16:00:00+00:00"},
    }
    events = _run_list_events(configured_provider, [raw])
    assert events[0].title == "(no title)"


# ---------------------------------------------------------------------------
# All-day events
# ---------------------------------------------------------------------------


def test_maps_all_day_event_correctly(configured_provider) -> None:
    """Google all-day events use `date` not `dateTime` and end is exclusive."""
    raw = {
        "id": "holiday",
        "summary": "Public holiday",
        "start": {"date": "2026-06-02"},
        "end": {"date": "2026-06-03"},  # Google's end is exclusive
    }
    events = _run_list_events(configured_provider, [raw])
    e = events[0]
    assert e.all_day is True
    assert e.start_at.date() == date(2026, 6, 2)
    # Our model uses inclusive end_at, so this should be 2026-06-02
    assert e.end_at.date() == date(2026, 6, 2)


# ---------------------------------------------------------------------------
# Meeting URL extraction
# ---------------------------------------------------------------------------


def test_extracts_hangout_link(configured_provider) -> None:
    """hangoutLink is the highest-priority source for the meeting URL."""
    items = [_make_timed_event(hangoutLink="https://meet.google.com/abc-def-ghi")]
    events = _run_list_events(configured_provider, items)
    assert events[0].meeting_url == "https://meet.google.com/abc-def-ghi"


def test_extracts_conference_data_video_url(configured_provider) -> None:
    """Falls back to conferenceData.entryPoints[].uri when hangoutLink absent."""
    items = [
        _make_timed_event(
            conferenceData={
                "entryPoints": [
                    {"entryPointType": "phone", "uri": "tel:+1234567890"},
                    {"entryPointType": "video", "uri": "https://zoom.us/j/123"},
                ]
            }
        )
    ]
    events = _run_list_events(configured_provider, items)
    assert events[0].meeting_url == "https://zoom.us/j/123"


def test_extracts_zoom_url_from_description(configured_provider) -> None:
    """Falls back to regex-scanning the description text."""
    items = [
        _make_timed_event(
            description="Join us at https://us02web.zoom.us/j/12345 for the meeting"
        )
    ]
    events = _run_list_events(configured_provider, items)
    assert events[0].meeting_url == "https://us02web.zoom.us/j/12345"


def test_extracts_teams_url(configured_provider) -> None:
    """Microsoft Teams URLs are recognized too."""
    items = [
        _make_timed_event(
            location="https://teams.microsoft.com/l/meetup-join/abc"
        )
    ]
    events = _run_list_events(configured_provider, items)
    assert events[0].meeting_url.startswith("https://teams.microsoft.com/")


def test_returns_none_when_no_meeting_url(configured_provider) -> None:
    """No URL in any field → meeting_url is None."""
    items = [_make_timed_event(description="Just text, no URL")]
    events = _run_list_events(configured_provider, items)
    assert events[0].meeting_url is None


# ---------------------------------------------------------------------------
# Defensive error handling
# ---------------------------------------------------------------------------


def test_api_exception_returns_empty(configured_provider) -> None:
    """If the API call raises, return [] rather than propagating."""
    fake_service = MagicMock()
    fake_service.events().list().execute.side_effect = RuntimeError("API down")

    fake_creds = MagicMock()
    fake_creds.expired = False

    with patch(CREDS_TARGET) as MockCreds, patch(BUILD_TARGET, return_value=fake_service):
        MockCreds.from_authorized_user_file.return_value = fake_creds
        result = configured_provider.list_events_for_range(
            date(2026, 6, 2), date(2026, 6, 2)
        )
    assert result == []


def test_credentials_failure_returns_empty(configured_provider) -> None:
    """If loading credentials raises, return [] rather than propagating."""
    with patch(CREDS_TARGET) as MockCreds:
        MockCreds.from_authorized_user_file.side_effect = RuntimeError("Bad token")
        result = configured_provider.list_events_for_range(
            date(2026, 6, 2), date(2026, 6, 2)
        )
    assert result == []


def test_expired_credentials_trigger_refresh(configured_provider, tmp_path) -> None:
    """An expired token gets refreshed and the new token persists."""
    fake_service = MagicMock()
    fake_service.events().list().execute.return_value = {"items": []}

    fake_creds = MagicMock()
    fake_creds.expired = True
    fake_creds.refresh_token = "refresh-token"
    fake_creds.to_json.return_value = '{"new": "token"}'

    with patch(CREDS_TARGET) as MockCreds, patch(BUILD_TARGET, return_value=fake_service):
        MockCreds.from_authorized_user_file.return_value = fake_creds
        configured_provider.list_events_for_range(
            date(2026, 6, 2), date(2026, 6, 2)
        )

    # refresh() should have been called
    fake_creds.refresh.assert_called_once()
    # And the new token should have been written back
    assert "new" in configured_provider._token_path.read_text()
