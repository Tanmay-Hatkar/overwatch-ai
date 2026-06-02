"""
google_calendar_provider.py — Real Google Calendar implementation.

NOTE: This is a stub for slice 7. The OAuth flow + real API calls land
when the user completes the Google Cloud Console setup and provides
`credentials.json`. Until then, this provider reports `is_configured()`
as False, which makes the CalendarService skip it and fall back to
whichever other provider is configured (typically `MockCalendarProvider`
in development).

Architecture intentionally separated:
  - This file knows about Google's OAuth2 + Calendar API only.
  - It returns generic `CalendarEvent` objects, never Google types.
  - Adding Outlook later means a sibling file, same interface.

To complete this provider, install:
    pip install google-api-python-client google-auth google-auth-oauthlib

Then implement the OAuth dance + `service.events().list()` call in
`list_events_for_date()`.
"""

import logging
from datetime import date
from pathlib import Path

from app.models.event import CalendarEvent
from app.providers.calendar_provider import CalendarProvider

logger = logging.getLogger(__name__)


class GoogleCalendarProvider(CalendarProvider):
    """
    Real Google Calendar provider — requires OAuth setup.

    Looks for `token.json` next to `credentials.json` in the backend
    directory. If neither exists, `is_configured()` returns False and
    the provider reports as unavailable.
    """

    source_name = "google"

    def __init__(
        self,
        credentials_file: str = "credentials.json",
        token_file: str = "token.json",
    ) -> None:
        self._credentials_path = Path(credentials_file)
        self._token_path = Path(token_file)

    def is_configured(self) -> bool:
        """Both credentials.json and token.json must exist."""
        return self._credentials_path.exists() and self._token_path.exists()

    def list_events_for_date(self, target_date: date) -> list[CalendarEvent]:
        """
        Slice-7 stub. Returns [] until the OAuth flow lands.

        Future implementation:
          1. Load credentials from token.json, refresh if expired
          2. Build the Google Calendar API service
          3. Call service.events().list(timeMin=..., timeMax=...)
          4. Map each item -> CalendarEvent
        """
        if not self.is_configured():
            logger.debug("GoogleCalendarProvider not configured; returning empty")
            return []

        logger.warning(
            "GoogleCalendarProvider real API call is not implemented yet. "
            "Returning empty list."
        )
        return []

    def list_events_for_range(
        self, start_date: date, end_date: date
    ) -> list[CalendarEvent]:
        """Slice-7 stub — see list_events_for_date()."""
        if not self.is_configured():
            return []
        logger.warning(
            "GoogleCalendarProvider real API call is not implemented yet."
        )
        return []
