"""
calendar.py — FastAPI routes for the calendar view.

  GET /calendar/today
    Returns events for today.

  GET /calendar/week
    Returns events for the current week (Monday through Sunday).

Both endpoints return empty arrays (not 503) if the configured provider
is unavailable — calendar context is supplementary, not critical.
"""

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends

from app.config import settings
from app.models.event import CalendarEvent
from app.providers.calendar_provider import CalendarProvider
from app.providers.empty_calendar_provider import EmptyCalendarProvider
from app.providers.google_calendar_provider import GoogleCalendarProvider
from app.providers.mock_calendar_provider import MockCalendarProvider
from app.services.calendar_service import CalendarService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/calendar", tags=["calendar"])


# ---------------------------------------------------------------------------
# Provider wiring — auto-detect at startup.
#
# If a Google OAuth token is present, use the real Google provider.
# Otherwise fall back to the mock provider so the calendar still renders
# something useful in development.
#
# Future slice 7b: a list of providers, settings-driven, possibly
# multiple Google accounts (work + personal).
# ---------------------------------------------------------------------------


def _select_provider() -> CalendarProvider:
    """
    Pick the best available provider at import time.

    Priority:
      1. Real Google Calendar — used whenever a token.json is present.
      2. In production (ENVIRONMENT=production) with no Google token,
         use EmptyCalendarProvider so the deployed app shows an honest
         empty grid instead of MockCalendarProvider's hardcoded fake
         events. Per-user calendar OAuth lands in a follow-up slice.
      3. In development with no Google token, use MockCalendarProvider
         so local dev has visible data to design against.
    """
    google = GoogleCalendarProvider()
    if google.is_configured():
        logger.info("Calendar: using GoogleCalendarProvider (real account)")
        return google
    if settings.environment == "production":
        logger.info(
            "Calendar: using EmptyCalendarProvider (no token configured; "
            "production mode hides mock data until per-user OAuth ships)"
        )
        return EmptyCalendarProvider()
    logger.info(
        "Calendar: using MockCalendarProvider (no token.json found — run "
        "scripts/setup_google_oauth.py to connect a real account)"
    )
    return MockCalendarProvider()


_provider: CalendarProvider = _select_provider()
_service = CalendarService(_provider)


def get_calendar_service() -> CalendarService:
    """FastAPI dependency that returns the configured CalendarService."""
    return _service


@router.get("/today", response_model=list[CalendarEvent])
def get_today_events(
    service: CalendarService = Depends(get_calendar_service),
) -> list[CalendarEvent]:
    """Return today's events sorted by start time."""
    today = datetime.now(UTC).date()
    return service.list_today(today)


@router.get("/week", response_model=list[CalendarEvent])
def get_week_events(
    service: CalendarService = Depends(get_calendar_service),
) -> list[CalendarEvent]:
    """
    Return this week's events (Monday through Sunday) sorted by start time.

    "This week" is computed from today's UTC date.
    """
    today = datetime.now(UTC).date()
    monday = today - timedelta(days=today.weekday())  # 0 = Monday
    sunday = monday + timedelta(days=6)
    return service.list_week(monday, sunday)
