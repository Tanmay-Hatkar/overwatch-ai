"""
google_oauth_service.py — Google OAuth 2.0 authorization code flow.

Owns the server-side half of "Sign in with Google":
  1. Build the authorization URL the user navigates to
  2. Exchange the returned `code` for an `id_token`
  3. Verify the id_token's signature + claims
  4. Return the decoded user info

For the calendar/gmail scopes used by the existing GoogleCalendarProvider,
see scripts/setup_google_oauth.py. That's a separate flow (offline access,
refresh tokens) — this module only handles the login scopes
(openid, email, profile).

Why a separate module from the calendar provider:
  - Different scopes (auth is openid/email/profile; calendar needs much more)
  - Different lifetimes (login id_tokens expire in 1 hour; we don't store
    them — we mint our own JWT after verification)
  - The OAuth library does the heavy lifting; this is mostly thin glue
"""

import logging
import secrets
from urllib.parse import urlencode

import requests
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from app.config import settings
from app.models.user import GoogleUserInfo

logger = logging.getLogger(__name__)


class OAuthError(Exception):
    """Raised when an OAuth step fails (network error, invalid code, etc.)."""


# Scopes for sign-in. Calendar/gmail scopes are requested separately by
# the calendar provider's OAuth flow if/when the user opts in to calendar
# sync — keeping the login scope minimal means a faster, less-scary consent
# screen for first-time users.
_LOGIN_SCOPES = ["openid", "email", "profile"]

_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"


def is_configured() -> bool:
    """
    Return True if Google OAuth client credentials are present.

    Used by /health and tests to detect misconfiguration up-front.
    """
    return bool(settings.google_client_id and settings.google_client_secret)


def generate_state() -> str:
    """
    Return a cryptographically random state value (CSRF protection).

    The caller stores this in a short-lived cookie before redirecting
    to Google; the callback compares the returned state against the
    cookie. A mismatch means the callback wasn't initiated by us.
    """
    return secrets.token_urlsafe(32)


def build_authorization_url(state: str) -> str:
    """
    Build the URL the user must navigate to in order to grant access.

    Args:
        state: A random CSRF token generated via generate_state().

    Returns:
        The full https://accounts.google.com/... URL with query params.

    Raises:
        OAuthError: If Google OAuth credentials are unconfigured.
    """
    if not is_configured():
        raise OAuthError(
            "Google OAuth client credentials are not configured. "
            "Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env."
        )

    params = {
        "response_type": "code",
        "client_id": settings.google_client_id,
        "redirect_uri": _redirect_uri(),
        "scope": " ".join(_LOGIN_SCOPES),
        "state": state,
        "access_type": "online",  # we don't need a refresh token for login
        "prompt": "select_account",  # let user pick which Google account
    }
    return f"{_AUTH_URL}?{urlencode(params)}"


def exchange_code_for_user(code: str) -> GoogleUserInfo:
    """
    Trade an authorization code for verified user information.

    This does two things:
      1. POST to Google's token endpoint with the code, getting back an
         id_token (and access_token, which we discard for login).
      2. Verify the id_token using google-auth's verifier, which checks
         the signature, issuer, audience, and expiry.

    Args:
        code: The `code` query param from /auth/google/callback.

    Returns:
        GoogleUserInfo with the verified sub, email, name, picture.

    Raises:
        OAuthError: If the token exchange fails, the id_token doesn't
            verify, or the user's email isn't verified.
    """
    if not is_configured():
        raise OAuthError("Google OAuth client credentials are not configured.")

    try:
        response = requests.post(
            _TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": _redirect_uri(),
                "grant_type": "authorization_code",
            },
            timeout=10,
        )
    except requests.RequestException as exc:
        logger.exception("Network error exchanging Google OAuth code")
        raise OAuthError("Network error contacting Google") from exc

    if not response.ok:
        # Google returns helpful JSON error bodies — log them for debugging.
        logger.error(
            "Google token endpoint returned %s: %s",
            response.status_code,
            response.text[:500],
        )
        raise OAuthError(
            f"Google rejected the authorization code (status {response.status_code})"
        )

    token_response = response.json()
    raw_id_token = token_response.get("id_token")
    if not raw_id_token:
        raise OAuthError("Google response did not include an id_token")

    # Verify signature, issuer, audience, expiry. This is the security
    # boundary — never trust the id_token's claims without this.
    #
    # clock_skew_in_seconds: google-auth defaults this to 0, so any
    # difference at all between this machine's clock and Google's — even
    # sub-second drift from an unsynced local clock — rejects an otherwise
    # valid token ("Token used too early"). 10s is the commonly-used
    # tolerance for exactly this (NTP drift, request latency); it doesn't
    # meaningfully weaken expiry/issued-at enforcement.
    try:
        idinfo = google_id_token.verify_oauth2_token(
            raw_id_token,
            google_requests.Request(),
            settings.google_client_id,
            clock_skew_in_seconds=10,
        )
    except ValueError as exc:
        logger.exception("Google id_token failed verification")
        raise OAuthError("Invalid id_token from Google") from exc

    if not idinfo.get("email_verified", False):
        raise OAuthError(
            "Google account's email is not verified — refusing sign-in."
        )

    return GoogleUserInfo(
        sub=idinfo["sub"],
        email=idinfo["email"],
        name=idinfo.get("name", idinfo["email"]),
        picture=idinfo.get("picture"),
        email_verified=True,
    )


def _redirect_uri() -> str:
    """Build the OAuth redirect URI from settings.backend_url."""
    return f"{settings.backend_url.rstrip('/')}/auth/google/callback"
