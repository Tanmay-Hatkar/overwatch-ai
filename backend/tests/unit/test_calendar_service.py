"""
test_calendar_service.py — Unit tests for CalendarService.

Most tests use MockCalendarProvider. A few tests verify the safety net
(exceptions in the provider don't bubble up — they return empty lists).
"""

from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest

from app.providers.calendar_provider import CalendarProvider
from app.providers.mock_calendar_provider import MockCalendarProvider
from app.services.calendar_service import CalendarService


@pytest.fixture
def service() -> CalendarService:
    """CalendarService wired to the mock provider."""
    return CalendarService(MockCalendarProvider())


def _next_weekday(d: date) -> date:
    """Helper: skip forward to a weekday (Mon-Fri)."""
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


def test_is_available_when_provider_configured(service: CalendarService) -> None:
    """The mock provider is always configured."""
    assert service.is_available is True


def test_list_today_returns_events_on_weekday(service: CalendarService) -> None:
    """On a weekday, the mock provider produces a small set of events."""
    today = _next_weekday(date.today())
    events = service.list_today(today)
    assert len(events) >= 1
    # Every event should be tagged with the provider's source
    assert all(e.source == "mock" for e in events)


def test_list_today_returns_empty_on_weekend(service: CalendarService) -> None:
    """The mock provider returns no events on weekends."""
    # Find the next Saturday
    today = date.today()
    while today.weekday() != 5:
        today += timedelta(days=1)
    events = service.list_today(today)
    assert events == []


def test_list_today_events_are_sorted_by_start(service: CalendarService) -> None:
    """Returned events are always sorted by start time."""
    today = _next_weekday(date.today())
    events = service.list_today(today)
    starts = [e.start_at for e in events]
    assert starts == sorted(starts)


def test_list_week_includes_multiple_days(service: CalendarService) -> None:
    """A 7-day range should include events across the included weekdays."""
    today = _next_weekday(date.today())
    end = today + timedelta(days=6)
    events = service.list_week(today, end)
    # On any 7-day span that includes at least one weekday, we expect events
    assert len(events) > 0


def test_list_week_is_sorted_by_start(service: CalendarService) -> None:
    """Week events are also sorted."""
    today = _next_weekday(date.today())
    end = today + timedelta(days=6)
    events = service.list_week(today, end)
    starts = [e.start_at for e in events]
    assert starts == sorted(starts)


# ---------------------------------------------------------------------------
# Failure handling
# ---------------------------------------------------------------------------


class _BrokenProvider(CalendarProvider):
    """A provider whose every call raises an exception."""

    source_name = "broken"

    def is_configured(self) -> bool:
        return True

    def list_events_for_date(self, target_date):
        raise RuntimeError("provider exploded")

    def list_events_for_range(self, start_date, end_date):
        raise RuntimeError("provider exploded")


def test_provider_exception_returns_empty_list() -> None:
    """A provider exception is caught — caller sees an empty list, not a crash."""
    service = CalendarService(_BrokenProvider())
    assert service.list_today(date.today()) == []
    assert service.list_week(date.today(), date.today() + timedelta(days=1)) == []


def test_is_available_false_when_provider_not_configured() -> None:
    """A provider that reports unconfigured propagates that to the service."""
    mock_provider = MagicMock(spec=CalendarProvider)
    mock_provider.is_configured.return_value = False
    service = CalendarService(mock_provider)
    assert service.is_available is False
