"""
calendar_provider.py — Abstract base for external calendar sources.

Subclasses implement one concrete source (Google, Outlook, Apple, mock).
The CalendarService composes ONE provider for slice 7; future slice 7b
can compose multiple providers (e.g., personal Google + work Outlook)
by holding a list.

Design notes:
  - Providers return CalendarEvent objects, never raw vendor types.
  - Providers do their own auth (loading tokens, refreshing them).
  - A provider that fails auth or has no credentials returns empty lists
    rather than raising — the calling code treats it as "no events"
    rather than crashing.
  - All datetimes are tz-aware (UTC). Callers convert to local for display.
"""

from abc import ABC, abstractmethod
from datetime import date

from app.models.event import CalendarEvent


class CalendarProvider(ABC):
    """
    Interface for a single calendar data source.

    Concrete implementations:
      - MockCalendarProvider: deterministic fake events, for dev + tests
      - GoogleCalendarProvider: real Google Calendar API
      - (Future) OutlookCalendarProvider, AppleCalendarProvider, ...
    """

    # A short stable identifier for this provider, e.g., "google", "mock".
    # Used as the `source` field on returned events and in logs.
    source_name: str = "abstract"

    @abstractmethod
    def is_configured(self) -> bool:
        """
        Returns True if this provider has valid credentials and can serve
        requests. Returns False if not yet configured (e.g., no OAuth
        token). Callers can use this to decide whether to include the
        provider in aggregation.
        """

    @abstractmethod
    def list_events_for_date(self, target_date: date) -> list[CalendarEvent]:
        """
        Return all events occurring on the given date (caller's timezone).

        Events that span midnight count as occurring on every day they touch.
        Returns an empty list if the provider isn't configured or the
        underlying API call fails.
        """

    @abstractmethod
    def list_events_for_range(
        self, start_date: date, end_date: date
    ) -> list[CalendarEvent]:
        """
        Return all events occurring within [start_date, end_date] inclusive.

        Returns an empty list if the provider isn't configured or the
        underlying API call fails.
        """
