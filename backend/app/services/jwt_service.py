"""
jwt_service.py — JWT issuance and verification for session cookies.

Wraps the `pyjwt` library with our own conventions:
  - Algorithm: HS256 (symmetric, signed with settings.session_secret)
  - Claims we issue:
      sub        Our internal user UUID (as string)
      iat        Issued-at (UTC seconds since epoch)
      exp        Expiry (UTC seconds since epoch)
  - We do NOT put email / name / google_id in the token — those live in
    the database and could go stale. The token just identifies WHO; we
    re-fetch profile data per request.

Why JWT and not server-side sessions: ADR-0009. TL;DR — stateless,
no DB lookup to validate, easier horizontal scaling.

Why not put profile in claims: a stale name in a JWT confuses users
("why is my display name wrong after I changed it on Google?"). Worth
the per-request user lookup to always have fresh data.
"""

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt

from app.config import settings

logger = logging.getLogger(__name__)

_ALGORITHM = "HS256"


class JWTError(Exception):
    """Raised when a JWT is invalid, expired, or malformed."""


def issue_session_token(user_id: UUID, max_age_days: int | None = None) -> str:
    """
    Sign and return a JWT identifying the given user.

    Args:
        user_id: Our internal UUID. Stored in the `sub` claim.
        max_age_days: Override the default token lifetime (settings.session_max_age_days).
            Used by /auth/me when refreshing a near-expiry token.

    Returns:
        The signed JWT as a compact string.

    Raises:
        ValueError: If session_secret is unset (misconfiguration).
    """
    if not settings.session_secret:
        raise ValueError(
            "SESSION_SECRET is not configured. Set it in .env before issuing tokens."
        )

    now = datetime.now(UTC)
    days = max_age_days if max_age_days is not None else settings.session_max_age_days
    expires_at = now + timedelta(days=days)

    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(payload, settings.session_secret, algorithm=_ALGORITHM)


def verify_session_token(token: str) -> UUID:
    """
    Verify a session JWT and return the user UUID it identifies.

    Args:
        token: The compact JWT from the session cookie.

    Returns:
        The user's UUID parsed from the `sub` claim.

    Raises:
        JWTError: If the token is expired, has an invalid signature,
            missing claims, or malformed.
    """
    if not settings.session_secret:
        raise JWTError("Server is not configured to verify sessions.")

    try:
        payload = jwt.decode(
            token,
            settings.session_secret,
            algorithms=[_ALGORITHM],
            options={"require": ["sub", "iat", "exp"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise JWTError("Session expired") from exc
    except jwt.InvalidTokenError as exc:
        # Catches bad signature, malformed token, missing required claims.
        raise JWTError("Invalid session token") from exc

    sub = payload.get("sub")
    if not isinstance(sub, str):
        raise JWTError("Session token missing sub claim")
    try:
        return UUID(sub)
    except ValueError as exc:
        raise JWTError("Session token sub is not a valid UUID") from exc


def should_refresh(token: str) -> bool:
    """
    Return True if the token is valid AND within the refresh window
    (settings.session_refresh_within_days of expiry).

    Used by /auth/me to silently extend long-lived sessions without
    forcing a re-login.

    Args:
        token: The compact JWT.

    Returns:
        True if the token should be reissued. False if it's still
        comfortably valid (or invalid — in which case verify_session_token
        would have already rejected the request).
    """
    try:
        payload = jwt.decode(
            token,
            settings.session_secret,
            algorithms=[_ALGORITHM],
            options={"require": ["exp"]},
        )
    except jwt.InvalidTokenError:
        return False

    exp = datetime.fromtimestamp(payload["exp"], tz=UTC)
    refresh_threshold = datetime.now(UTC) + timedelta(
        days=settings.session_refresh_within_days
    )
    return exp <= refresh_threshold
