"""
empty_calendar_provider.py — A calendar provider that returns no events.

Used in production when no real calendar is connected yet. Lets the
frontend render the weekly grid honestly (empty), instead of showing
the developer-only MockCalendarProvider with its hardcoded fake events.

When per-user Google Calendar OAuth lands (slice 12), this provider
becomes the default for users who haven't connected their account yet,
and GoogleCalendarProvider takes over for users who have.
"""

from datetime import date

from app.models.event import CalendarEvent
from app.providers.calendar_provider import CalendarProvider


class EmptyCalendarProvider(CalendarProvider):
    """
    No-op calendar provider. Always reports as "configured" (so the
    routes don't fall back further) but returns no events for any query.
    """

    source_name = "empty"

    def is_configured(self) -> bool:
        return True

    def list_events_for_date(self, target_date: date) -> list[CalendarEvent]:
        return []

    def list_events_for_range(
        self, start_date: date, end_date: date
    ) -> list[CalendarEvent]:
        return []
