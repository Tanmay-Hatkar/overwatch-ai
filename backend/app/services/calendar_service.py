"""
calendar_service.py — Read events from one or more CalendarProvider(s).

For slice 7, the service holds ONE provider (Mock or Google). Slice 7b
will extend this to a list of providers so events from work + personal
accounts merge into a single view.

Failure mode: if a provider's API call raises, we log + return an empty
list rather than letting the exception bubble. Calendar context is
nice-to-have, not critical; the rest of the app should keep working
even if Google is down.
"""

import logging
from datetime import date

from app.models.event import CalendarEvent
from app.providers.calendar_provider import CalendarProvider

logger = logging.getLogger(__name__)


class CalendarService:
    """
    Returns events from the configured calendar provider.

    Wraps the provider in defensive error handling — failures degrade
    gracefully to empty event lists rather than crashing the request.
    """

    def __init__(self, provider: CalendarProvider) -> None:
        self._provider = provider

    @property
    def is_available(self) -> bool:
        """Whether the underlying provider can be queried right now."""
        return self._provider.is_configured()

    def list_today(self, today: date) -> list[CalendarEvent]:
        """Return today's events, sorted by start time."""
        return self._safely(
            lambda: self._provider.list_events_for_date(today),
            f"list_today({today})",
        )

    def list_week(self, start: date, end: date) -> list[CalendarEvent]:
        """Return events for [start, end] inclusive, sorted by start time."""
        return self._safely(
            lambda: self._provider.list_events_for_range(start, end),
            f"list_week({start}..{end})",
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _safely(self, fetch_fn, label: str) -> list[CalendarEvent]:
        """Run a provider fetch; on exception, log + return empty."""
        try:
            events = fetch_fn()
        except Exception as e:
            logger.warning(f"Calendar provider failed in {label}: {e}")
            return []
        # Always sort by start time so callers don't need to.
        return sorted(events, key=lambda e: e.start_at)
