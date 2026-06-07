"""
google_calendar_oauth.py — OAuth flow for connecting a user's Google
Calendar (read-only).

Distinct from google_oauth_service (which handles *login* — openid/email/
profile, no stored tokens). This module requests the calendar.readonly
scope with offline access so Google returns a refresh token, and returns
the full credential set for persistence in google_calendar_tokens.

Security: the returned access/refresh tokens are sensitive. Callers store
them in the database (never the repo) and only ever transmit them to
Google's token endpoint.
"""

import logging
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import requests

from app.config import settings

logger = logging.getLogger(__name__)


class CalendarOAuthError(Exception):
    """Raised when a calendar OAuth step fails."""


# Read-only calendar access — we never write to the user's calendar.
CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"


def is_configured() -> bool:
    """True if the Google OAuth client credentials are present."""
    return bool(settings.google_client_id and settings.google_client_secret)


def generate_state() -> str:
    """Return a random CSRF state token (stored in a short-lived cookie)."""
    return secrets.token_urlsafe(32)


def redirect_uri() -> str:
    """Build the calendar-connect redirect URI from settings.backend_url."""
    return f"{settings.backend_url.rstrip('/')}/calendar/connect/google/callback"


def build_authorization_url(state: str) -> str:
    """
    Build the Google consent URL for calendar access.

    Args:
        state: A random CSRF token from generate_state().

    Returns:
        The full accounts.google.com authorization URL.

    Raises:
        CalendarOAuthError: If client credentials are not configured.
    """
    if not is_configured():
        raise CalendarOAuthError(
            "Google OAuth client credentials are not configured."
        )

    params = {
        "response_type": "code",
        "client_id": settings.google_client_id,
        "redirect_uri": redirect_uri(),
        "scope": " ".join(CALENDAR_SCOPES),
        "state": state,
        # offline + consent => Google returns a refresh token so we can
        # keep reading events after the access token expires.
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
    }
    return f"{_AUTH_URL}?{urlencode(params)}"


def exchange_code_for_credentials(code: str) -> dict:
    """
    Trade an authorization code for OAuth credentials.

    Args:
        code: The `code` query param from the calendar callback.

    Returns:
        A dict ready for GoogleCalendarTokensRepository.upsert():
        access_token, refresh_token, token_uri, client_id, client_secret,
        scopes, expiry (ISO 8601 or None).

    Raises:
        CalendarOAuthError: If the exchange fails or returns no access token.
    """
    if not is_configured():
        raise CalendarOAuthError(
            "Google OAuth client credentials are not configured."
        )

    try:
        response = requests.post(
            _TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": redirect_uri(),
                "grant_type": "authorization_code",
            },
            timeout=10,
        )
    except requests.RequestException as exc:
        logger.exception("Network error exchanging calendar OAuth code")
        raise CalendarOAuthError("Network error contacting Google") from exc

    if not response.ok:
        logger.error(
            "Calendar token endpoint returned %s: %s",
            response.status_code,
            response.text[:500],
        )
        raise CalendarOAuthError(
            f"Google rejected the authorization code (status {response.status_code})"
        )

    data = response.json()
    access_token = data.get("access_token")
    if not access_token:
        raise CalendarOAuthError("Google response did not include an access_token")

    # Convert expires_in (seconds) to an absolute ISO timestamp.
    expiry: str | None = None
    expires_in = data.get("expires_in")
    if isinstance(expires_in, (int, float)):
        expiry = (datetime.now(UTC) + timedelta(seconds=expires_in)).isoformat()

    return {
        "access_token": access_token,
        "refresh_token": data.get("refresh_token"),
        "token_uri": _TOKEN_URL,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "scopes": data.get("scope", " ".join(CALENDAR_SCOPES)),
        "expiry": expiry,
    }
