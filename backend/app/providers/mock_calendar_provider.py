"""
mock_calendar_provider.py — Deterministic fake calendar provider.

Used in development (when no real Google credentials are present) and in
tests. Returns a small set of realistic events for the current date so
the UI looks populated even without OAuth set up.

Event generation:
  - Today: 3 events at fixed times (standup, lunch meeting, 1:1)
  - Tomorrow: 1 event (planning session)
  - Other days in the week: 1-2 events with predictable times based on weekday

This is deterministic so tests can assert on the exact output.
"""

from datetime import UTC, date, datetime, timedelta

from app.models.event import CalendarEvent
from app.providers.calendar_provider import CalendarProvider


def _at(target_date: date, hour: int, minute: int = 0) -> datetime:
    """Helper: build a UTC datetime on the given date at given hour:minute."""
    return datetime(
        target_date.year,
        target_date.month,
        target_date.day,
        hour,
        minute,
        tzinfo=UTC,
    )


# Base set of events that appear "today" — keyed by name for stability
_TODAY_TEMPLATE = [
    {
        "id": "mock-standup",
        "title": "Daily standup",
        "start_hour": 9,
        "start_min": 30,
        "end_hour": 9,
        "end_min": 45,
        "location": "Zoom",
        "meeting_url": "https://zoom.us/j/mock-standup",
    },
    {
        "id": "mock-lunch",
        "title": "Lunch with Alex",
        "start_hour": 12,
        "start_min": 30,
        "end_hour": 13,
        "end_min": 30,
        "location": "Mucho Burrito",
        "meeting_url": None,
    },
    {
        "id": "mock-1on1",
        "title": "1:1 with manager",
        "start_hour": 15,
        "start_min": 0,
        "end_hour": 15,
        "end_min": 30,
        "location": "Google Meet",
        "meeting_url": "https://meet.google.com/mock-abc-def",
    },
]


class MockCalendarProvider(CalendarProvider):
    """A deterministic provider that returns plausible-looking events."""

    source_name = "mock"

    def is_configured(self) -> bool:
        """Mock provider is always available."""
        return True

    def list_events_for_date(self, target_date: date) -> list[CalendarEvent]:
        """Generate events for the given date based on the template + weekday."""
        events: list[CalendarEvent] = []

        # Skip weekends — show realistic "no events" state
        if target_date.weekday() >= 5:
            return events

        for template in _TODAY_TEMPLATE:
            events.append(
                CalendarEvent(
                    id=f"{template['id']}-{target_date.isoformat()}",
                    source=self.source_name,
                    title=template["title"],
                    start_at=_at(target_date, template["start_hour"], template["start_min"]),
                    end_at=_at(target_date, template["end_hour"], template["end_min"]),
                    all_day=False,
                    location=template["location"],
                    description=None,
                    meeting_url=template["meeting_url"],
                    color="#4285f4",  # Google blue
                )
            )

        return events

    def list_events_for_range(
        self, start_date: date, end_date: date
    ) -> list[CalendarEvent]:
        """Aggregate events across the inclusive date range."""
        events: list[CalendarEvent] = []
        current = start_date
        while current <= end_date:
            events.extend(self.list_events_for_date(current))
            current += timedelta(days=1)
        return events
