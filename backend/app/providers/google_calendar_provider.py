"""
google_calendar_provider.py — Real Google Calendar implementation.

Reads OAuth credentials from `token.json` (next to `credentials.json` in
the backend directory). If neither exists, `is_configured()` returns
False and the provider reports as unavailable — the CalendarService
falls back to whichever other provider is configured.

Token auto-refresh: when the access token expires, google-auth refreshes
it automatically using the refresh token. If the refresh fails (e.g.,
the user revoked access), we log + return empty rather than crashing.

Scope: calendar.readonly. We never write to the user's calendar.
"""

import logging
import re
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from app.models.event import CalendarEvent
from app.providers.calendar_provider import CalendarProvider

logger = logging.getLogger(__name__)

# Scopes matching the v1 token (which we reuse here):
#   - calendar       — read+write access to the user's calendars
#   - gmail.readonly — read-only Gmail (for future meeting-prep briefings)
#
# We only USE calendar.readonly capability today; the broader grant
# avoids forcing a second OAuth dance when we add Gmail context later.
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.readonly",
]

# Regex patterns to recognize popular meeting URLs in the description
# or location. Stops at whitespace or end of string.
_MEETING_URL_PATTERNS = [
    re.compile(r"https?://[^\s]*zoom\.us/[^\s]+", re.IGNORECASE),
    re.compile(r"https?://meet\.google\.com/[^\s]+", re.IGNORECASE),
    re.compile(r"https?://teams\.microsoft\.com/[^\s]+", re.IGNORECASE),
    re.compile(r"https?://[^\s]*webex\.com/[^\s]+", re.IGNORECASE),
]


class GoogleCalendarProvider(CalendarProvider):
    """
    Real Google Calendar provider — requires OAuth setup.

    See `scripts/setup_google_oauth.py` for the one-time setup flow
    that produces `token.json`.
    """

    source_name = "google"

    def __init__(
        self,
        credentials_file: str = "credentials.json",
        token_file: str = "token.json",
        calendar_id: str = "primary",
        *,
        credentials: Credentials | None = None,
        on_refresh: Callable[[Credentials], None] | None = None,
    ) -> None:
        """
        Two construction modes:

          - File-backed (default): reads credentials from token_file on
            disk. Used in local development with scripts/setup_google_oauth.py.
          - Credentials-backed: pass a pre-built `credentials` object (e.g.
            reconstructed from a database row). `on_refresh` is invoked with
            the refreshed Credentials so the caller can persist the new
            access token. This is how the hosted, per-user flow works.

        Args:
            credentials_file: Path to the OAuth client secrets (file mode).
            token_file: Path to the stored token JSON (file mode).
            calendar_id: Which calendar to read; "primary" by default.
            credentials: Pre-built credentials (DB mode). Takes precedence.
            on_refresh: Callback(creds) invoked after a token refresh (DB mode).
        """
        self._credentials_path = Path(credentials_file)
        self._token_path = Path(token_file)
        self._calendar_id = calendar_id
        self._creds = credentials
        self._on_refresh = on_refresh

    @classmethod
    def from_token_row(
        cls,
        row: dict,
        on_refresh: Callable[[Credentials], None] | None = None,
        calendar_id: str = "primary",
    ) -> "GoogleCalendarProvider":
        """
        Build a provider from a stored google_calendar_tokens row.

        Args:
            row: A dict from GoogleCalendarTokensRepository.get() with
                access_token, refresh_token, token_uri, client_id,
                client_secret, scopes, expiry.
            on_refresh: Callback invoked with refreshed Credentials so the
                caller can persist the new access token to the DB.
            calendar_id: Which calendar to read.

        Returns:
            A credentials-backed GoogleCalendarProvider.
        """
        expiry = None
        if row.get("expiry"):
            try:
                parsed = datetime.fromisoformat(row["expiry"])
                # google-auth expects a NAIVE UTC datetime for expiry.
                expiry = parsed.astimezone(UTC).replace(tzinfo=None)
            except (ValueError, TypeError):
                logger.warning("calendar: bad stored expiry %r", row.get("expiry"))

        creds = Credentials(
            token=row["access_token"],
            refresh_token=row.get("refresh_token"),
            token_uri=row.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=row["client_id"],
            client_secret=row["client_secret"],
            scopes=(row.get("scopes") or "").split() or None,
        )
        creds.expiry = expiry
        return cls(credentials=creds, on_refresh=on_refresh, calendar_id=calendar_id)

    def is_configured(self) -> bool:
        """
        Configured if we have credentials directly (DB mode) OR both
        credentials.json and token.json exist on disk (file mode).
        """
        if self._creds is not None:
            return True
        return self._credentials_path.exists() and self._token_path.exists()

    def list_events_for_date(self, target_date: date) -> list[CalendarEvent]:
        """Fetch a single day's events."""
        return self.list_events_for_range(target_date, target_date)

    def list_events_for_range(
        self, start_date: date, end_date: date
    ) -> list[CalendarEvent]:
        """
        Fetch all events in [start_date, end_date] inclusive.

        Defensive: any failure (auth, network, API) returns an empty list
        with a logged warning. Calendar context is supplementary; we don't
        want to crash the briefing or week view because Google had a hiccup.
        """
        if not self.is_configured():
            return []

        try:
            service = self._build_service()
        except Exception as e:
            logger.warning(f"Google Calendar: failed to build service: {e}")
            return []

        # Inclusive range — start at 00:00 of start_date, end at 23:59:59 of end_date.
        time_min = datetime.combine(
            start_date, datetime.min.time(), tzinfo=UTC
        ).isoformat()
        time_max = datetime.combine(
            end_date, datetime.max.time(), tzinfo=UTC
        ).isoformat()

        try:
            response = (
                service.events()
                .list(
                    calendarId=self._calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,  # expand recurring events into instances
                    orderBy="startTime",
                    maxResults=100,
                )
                .execute()
            )
        except Exception as e:
            logger.warning(f"Google Calendar: events().list() failed: {e}")
            return []

        items = response.get("items", [])
        return [self._map_to_event(item) for item in items if item.get("start")]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_service(self):
        """
        Load credentials, refresh if needed, build the Calendar API client.

        Side effect on refresh:
          - DB mode: invoke on_refresh(creds) so the caller persists the
            new access token to google_calendar_tokens.
          - File mode: write the refreshed token back to disk.
        """
        if self._creds is not None:
            creds = self._creds
        else:
            creds = Credentials.from_authorized_user_file(
                str(self._token_path), SCOPES
            )

        # Refresh expired credentials. If there's no refresh token, this
        # raises and we fall through to the empty-list path upstream.
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            if self._creds is not None:
                # DB mode — hand the refreshed creds back for persistence.
                if self._on_refresh is not None:
                    self._on_refresh(creds)
            else:
                # File mode — persist so next call skips the refresh.
                self._token_path.write_text(creds.to_json())

        return build("calendar", "v3", credentials=creds, cache_discovery=False)

    @classmethod
    def _map_to_event(cls, item: dict[str, Any]) -> CalendarEvent:
        """Map one Google event object to our CalendarEvent model."""
        # Google represents "all-day" events with a `date` field instead of
        # `dateTime`. Timed events use `dateTime` with timezone offset.
        start_field = item["start"]
        end_field = item.get("end", {})

        if "dateTime" in start_field:
            start_at = datetime.fromisoformat(start_field["dateTime"])
            end_at = datetime.fromisoformat(
                end_field.get("dateTime", start_field["dateTime"])
            )
            all_day = False
        else:
            # All-day event: "YYYY-MM-DD" → midnight UTC start, end at 23:59:59 UTC
            start_date = date.fromisoformat(start_field["date"])
            end_date_str = end_field.get("date", start_field["date"])
            # Google's `end.date` is EXCLUSIVE — subtract a day for our model
            end_date_value = date.fromisoformat(end_date_str) - timedelta(days=1)
            start_at = datetime.combine(start_date, datetime.min.time(), tzinfo=UTC)
            end_at = datetime.combine(end_date_value, datetime.max.time(), tzinfo=UTC)
            all_day = True

        # Normalize timezone — Pydantic wants tz-aware datetimes
        if start_at.tzinfo is None:
            start_at = start_at.replace(tzinfo=timezone.utc)
        if end_at.tzinfo is None:
            end_at = end_at.replace(tzinfo=timezone.utc)

        return CalendarEvent(
            id=item["id"],
            source=cls.source_name,
            title=item.get("summary", "(no title)"),
            start_at=start_at,
            end_at=end_at,
            all_day=all_day,
            location=item.get("location"),
            description=item.get("description"),
            meeting_url=cls._extract_meeting_url(item),
            color=None,  # Google's `colorId` maps to user palette; skip for now
        )

    @staticmethod
    def _extract_meeting_url(item: dict[str, Any]) -> str | None:
        """
        Try to find a Zoom/Meet/Teams/Webex URL.

        Order of precedence:
          1. `hangoutLink` (Google Meet, set automatically)
          2. `conferenceData.entryPoints[].uri` where entryPointType=="video"
          3. Regex scan of `description` and `location`
        """
        hangout = item.get("hangoutLink")
        if hangout:
            return hangout

        conf = item.get("conferenceData") or {}
        for entry in conf.get("entryPoints", []):
            if entry.get("entryPointType") == "video" and entry.get("uri"):
                return entry["uri"]

        # Fall back to scanning text fields
        text_blob = f"{item.get('description') or ''}\n{item.get('location') or ''}"
        for pattern in _MEETING_URL_PATTERNS:
            match = pattern.search(text_blob)
            if match:
                return match.group(0)

        return None
