"""
calendar.py — FastAPI routes for reading the user's calendar.

Display (per signed-in user):
  GET /calendar/today        Events for today.
  GET /calendar/week         Events for the current week (Mon–Sun).
  GET /calendar/connection   {connected: bool} — has the user linked Google?

  POST /calendar/disconnect  Remove the stored tokens.

The browser-based "connect" flow was removed with the web client
(ADR-0024): it authenticated the callback with the web session cookie,
which the mobile app doesn't have. Re-adding connect for mobile needs a
callback that identifies the user without a cookie (e.g. a signed state).

Display endpoints return empty arrays (not 503) if the provider is
unavailable — calendar context is supplementary, not critical.

Provider selection per user:
  - user has a stored token  → GoogleCalendarProvider (real events)
  - else, production          → EmptyCalendarProvider (honest empty grid)
  - else, development         → MockCalendarProvider (visible test data)

briefings.py still imports get_calendar_service() (the default singleton)
for its calendar context; that path is not user-scoped yet (see ADR-0011).
"""

import logging
import sqlite3
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, status

from app.config import settings
from app.database import get_db
from app.models.event import CalendarEvent
from app.models.user import UserResponse
from app.providers.calendar_provider import CalendarProvider
from app.providers.empty_calendar_provider import EmptyCalendarProvider
from app.providers.google_calendar_provider import GoogleCalendarProvider
from app.providers.mock_calendar_provider import MockCalendarProvider
from app.repositories.google_calendar_tokens_repository import (
    GoogleCalendarTokensRepository,
)
from app.routes.auth import current_user
from app.services.calendar_service import CalendarService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/calendar", tags=["calendar"])

# ---------------------------------------------------------------------------
# Default (non-user-scoped) provider singleton — used by briefings.py.
#
# This preserves the pre-existing get_calendar_service() dependency that
# briefings rely on. It never returns a real user's events; per-user events
# come through the display routes below.
# ---------------------------------------------------------------------------


def _select_default_provider() -> CalendarProvider:
    """Pick the default provider for non-user-scoped callers (briefings)."""
    if settings.environment == "production":
        return EmptyCalendarProvider()
    return MockCalendarProvider()


_default_service = CalendarService(_select_default_provider())


def get_calendar_service() -> CalendarService:
    """FastAPI dependency returning the default (non-user) CalendarService."""
    return _default_service


# ---------------------------------------------------------------------------
# Per-user provider construction (for the display routes).
# ---------------------------------------------------------------------------


def _build_user_calendar_service(
    user: UserResponse, conn: sqlite3.Connection
) -> CalendarService:
    """
    Build a CalendarService for one user from their stored Google token.

    When the user has connected their calendar, the provider refreshes the
    access token as needed and persists the refreshed token back via the
    on_refresh callback (which reuses this request's DB connection).
    """
    repo = GoogleCalendarTokensRepository(conn)
    row = repo.get(user.id)

    if row is not None:
        def on_refresh(creds) -> None:
            try:
                repo.upsert(
                    user.id,
                    access_token=creds.token,
                    refresh_token=creds.refresh_token,
                    token_uri=creds.token_uri,
                    client_id=creds.client_id,
                    client_secret=creds.client_secret,
                    scopes=" ".join(creds.scopes or []),
                    expiry=creds.expiry.isoformat() if creds.expiry else None,
                )
            except Exception:  # noqa: BLE001 — refresh persistence is best-effort
                logger.warning("calendar: failed to persist refreshed token", exc_info=True)

        provider: CalendarProvider = GoogleCalendarProvider.from_token_row(
            row, on_refresh=on_refresh
        )
        return CalendarService(provider)

    if settings.environment == "production":
        return CalendarService(EmptyCalendarProvider())
    return CalendarService(MockCalendarProvider())


# ---------------------------------------------------------------------------
# Display endpoints
# ---------------------------------------------------------------------------


@router.get("/today", response_model=list[CalendarEvent])
def get_today_events(
    user: UserResponse = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
) -> list[CalendarEvent]:
    """Return the signed-in user's events for today."""
    service = _build_user_calendar_service(user, conn)
    today = datetime.now(UTC).date()
    return service.list_today(today)


@router.get("/week", response_model=list[CalendarEvent])
def get_week_events(
    user: UserResponse = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
) -> list[CalendarEvent]:
    """
    Return the signed-in user's events for this week (Monday–Sunday),
    sorted by start time. "This week" is computed from today's UTC date.
    """
    service = _build_user_calendar_service(user, conn)
    today = datetime.now(UTC).date()
    monday = today - timedelta(days=today.weekday())  # 0 = Monday
    sunday = monday + timedelta(days=6)
    return service.list_week(monday, sunday)


@router.get("/connection")
def get_connection_status(
    user: UserResponse = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict[str, bool]:
    """Report whether the signed-in user has connected their Google Calendar."""
    repo = GoogleCalendarTokensRepository(conn)
    return {"connected": repo.get(user.id) is not None}


@router.post("/disconnect", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_google(
    user: UserResponse = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
) -> None:
    """Remove the user's stored Google Calendar tokens. Idempotent."""
    repo = GoogleCalendarTokensRepository(conn)
    repo.delete(user.id)
