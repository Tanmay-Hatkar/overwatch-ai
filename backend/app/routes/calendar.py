"""
calendar.py — FastAPI routes for the calendar view.

  GET /calendar/today
    Returns events for today.

  GET /calendar/week
    Returns events for the current week (Monday through Sunday).

Both endpoints return empty arrays (not 503) if the configured provider
is unavailable — calendar context is supplementary, not critical.
"""

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends

from app.models.event import CalendarEvent
from app.providers.calendar_provider import CalendarProvider
from app.providers.mock_calendar_provider import MockCalendarProvider
from app.services.calendar_service import CalendarService

router = APIRouter(prefix="/calendar", tags=["calendar"])


# ---------------------------------------------------------------------------
# Provider wiring
#
# In slice 7, we instantiate ONE provider at startup. The choice is hardcoded
# below: MockCalendarProvider for now. When the user completes OAuth, we
# swap this to GoogleCalendarProvider (one-line change).
#
# Future slice 7b: a list of providers, settings-driven.
# ---------------------------------------------------------------------------

_provider: CalendarProvider = MockCalendarProvider()
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
