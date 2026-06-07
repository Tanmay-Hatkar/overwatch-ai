"""
calendar.py — FastAPI routes for the calendar view + Google Calendar connect.

Display (per signed-in user):
  GET /calendar/today        Events for today.
  GET /calendar/week         Events for the current week (Mon–Sun).
  GET /calendar/connection   {connected: bool} — has the user linked Google?

Connect flow (per signed-in user):
  GET  /calendar/connect/google           Redirect to Google's consent screen.
  GET  /calendar/connect/google/callback  Store the granted tokens.
  POST /calendar/disconnect               Remove the stored tokens.

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

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse

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
from app.services import google_calendar_oauth
from app.services.calendar_service import CalendarService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/calendar", tags=["calendar"])

# Short-lived cookie carrying the OAuth state between connect + callback.
_CAL_STATE_COOKIE = "ow_cal_oauth_state"
_CAL_STATE_MAX_AGE_SECONDS = 600  # 10 minutes


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


# ---------------------------------------------------------------------------
# Connect flow
# ---------------------------------------------------------------------------


@router.get("/connect/google")
def connect_google(user: UserResponse = Depends(current_user)) -> RedirectResponse:
    """
    Start the calendar OAuth flow: set a state cookie and 302 to Google.

    Requires an authenticated user — only a signed-in user can link a
    calendar to their account.
    """
    if not google_calendar_oauth.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Calendar connect is not configured on this server.",
        )

    state = google_calendar_oauth.generate_state()
    auth_url = google_calendar_oauth.build_authorization_url(state)

    response = RedirectResponse(url=auth_url, status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key=_CAL_STATE_COOKIE,
        value=state,
        max_age=_CAL_STATE_MAX_AGE_SECONDS,
        httponly=True,
        secure=settings.environment == "production",
        samesite="lax",
        path="/",
    )
    return response


@router.get("/connect/google/callback")
def connect_google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    user: UserResponse = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
) -> RedirectResponse:
    """
    Receive Google's redirect, verify state, exchange the code, store the
    tokens for the user, then redirect back to the frontend.
    """
    if error:
        logger.info("Calendar OAuth callback returned error: %s", error)
        return _redirect_to_frontend(calendar="denied")

    if not code or not state:
        return _redirect_to_frontend(calendar="missing_code")

    expected_state = request.cookies.get(_CAL_STATE_COOKIE)
    if not expected_state or expected_state != state:
        logger.warning("Calendar OAuth state mismatch — possible CSRF or expired flow")
        return _redirect_to_frontend(calendar="state_mismatch")

    try:
        creds = google_calendar_oauth.exchange_code_for_credentials(code)
    except google_calendar_oauth.CalendarOAuthError:
        logger.exception("Failed to exchange calendar OAuth code")
        return _redirect_to_frontend(calendar="exchange_failed")

    repo = GoogleCalendarTokensRepository(conn)
    repo.upsert(
        user.id,
        access_token=creds["access_token"],
        refresh_token=creds["refresh_token"],
        token_uri=creds["token_uri"],
        client_id=creds["client_id"],
        client_secret=creds["client_secret"],
        scopes=creds["scopes"],
        expiry=creds["expiry"],
    )
    logger.info("Calendar connected for user %s", user.id)

    response = _redirect_to_frontend(calendar="connected")
    response.delete_cookie(
        key=_CAL_STATE_COOKIE,
        path="/",
        secure=settings.environment == "production",
        httponly=True,
        samesite="lax",
    )
    return response


@router.post("/disconnect", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_google(
    user: UserResponse = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
) -> None:
    """Remove the user's stored Google Calendar tokens. Idempotent."""
    repo = GoogleCalendarTokensRepository(conn)
    repo.delete(user.id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _redirect_to_frontend(calendar: str) -> RedirectResponse:
    """
    Redirect back to the frontend after the connect flow, with a
    ?calendar=<status> query param the UI can surface (toast/banner).
    """
    base = settings.frontend_url.rstrip("/")
    return RedirectResponse(
        url=f"{base}/?calendar={calendar}",
        status_code=status.HTTP_302_FOUND,
    )
