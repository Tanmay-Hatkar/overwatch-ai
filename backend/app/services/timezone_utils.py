"""
timezone_utils.py — Shared helper for resolving a browser-supplied IANA
timezone name into a ZoneInfo, with a safe UTC fallback.

Extracted from ChatService (the original caller) so BriefingService and
ReflectionService can use the exact same "what day is 'today'" semantics
instead of each computing 'today' against a different clock (server-local
date, or raw UTC) — see ADR-0023's follow-up: date bucketing keyed off UTC
alone is wrong for any user not near UTC for a large chunk of every day.
"""

import logging
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)


def resolve_timezone(tz_name: str | None) -> ZoneInfo:
    """
    Turn a browser-supplied IANA timezone name into a ZoneInfo.

    Falls back to UTC if the name is missing or unrecognized — the
    server's clock is reliable (NTP); the only thing we don't know
    without the client is which wall clock to render it against.
    """
    if tz_name:
        try:
            return ZoneInfo(tz_name)
        except (ZoneInfoNotFoundError, ValueError):
            logger.warning("unknown timezone %r, defaulting to UTC", tz_name)
    return ZoneInfo("UTC")


def to_user_date(dt: datetime, user_tz: ZoneInfo) -> date:
    """
    Return dt's calendar date as seen in user_tz.

    Treats a naive dt as already UTC rather than calling .astimezone()
    directly on it — Python interprets a naive datetime's .astimezone() as
    "this is in the *system's local* time," which is wrong here and, on a
    non-UTC server/dev machine, silently shifts the date. due_at/updated_at
    are supposed to always be stored UTC-aware (chat capture always attaches
    a timezone before saving), but a naive value can still arrive via a
    direct API call whose ISO string has no offset — this keeps that case
    safe instead of misdating it.
    """
    aware = dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
    return aware.astimezone(user_tz).date()
