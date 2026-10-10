"""
auth.py — Authentication routes (Google OAuth + bearer-token sessions).

Endpoints:
  GET  /auth/google/login      Redirect to Google's consent screen
  GET  /auth/google/callback   Receive code from Google, deep-link a session
                               token into the mobile app (overwatch://auth)
  GET  /auth/me                Return the current user. 401 if not signed in.
  POST /auth/logout            No-op acknowledgement (sessions are stateless
                               bearer JWTs; the app discards its own token).

The mobile app is the only client (ADR-0024), so sessions are carried as
`Authorization: Bearer <jwt>` — no session cookie. The only cookie left is
the short-lived OAuth `state` cookie, which lives in the system browser
for the duration of the sign-in flow (CSRF protection).

The current_user FastAPI dependency lives at the bottom of this module
and is imported by other routes for auth-gating.
"""

import logging
import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from app.config import is_email_allowed, settings
from app.database import get_db
from app.models.user import UserResponse
from app.repositories.user_repository import UserRepository
from app.services import google_oauth_service
from app.services.jwt_service import JWTError, issue_session_token, verify_session_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# Short-lived cookie name carrying the OAuth `state` between /login and
# /callback. Used solely for CSRF protection on the OAuth flow.
_STATE_COOKIE = "ow_oauth_state"
_STATE_COOKIE_MAX_AGE_SECONDS = 600  # 10 minutes

# Custom URL scheme the mobile app registers (mobile/app.json `scheme`).
# The callback deep-links here with the session token so the app can store it.
_NATIVE_REDIRECT_SCHEME = "overwatch"


def _build_repo(conn: sqlite3.Connection = Depends(get_db)) -> UserRepository:
    """FastAPI dependency that wires a UserRepository to the request's DB connection."""
    return UserRepository(conn)


def _bearer_token(authorization: str | None) -> str | None:
    """
    Extract the session token from an `Authorization: Bearer <token>` header.

    Args:
        authorization: Value of the Authorization header, if any.

    Returns:
        The token string, or None if the header is missing or not a bearer.
    """
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip() or None
    return None


def _user_from_token(token: str | None, repo: UserRepository) -> UserResponse:
    """
    Resolve a bearer token to its user, or raise 401.

    Args:
        token: The session JWT, or None.
        repo: UserRepository for the lookup.

    Returns:
        The matching UserResponse.

    Raises:
        401 if the token is missing, invalid/expired, or the user no longer exists.
    """
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not signed in")
    try:
        user_id = verify_session_token(token)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session invalid or expired",
        ) from exc

    user = repo.get_by_id(user_id)
    if user is None:
        # User row was deleted but their token is still floating around.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists",
        )
    return user


@router.get("/google/login")
def google_login() -> RedirectResponse:
    """
    Start the OAuth flow. Sets a short-lived state cookie and 302s to Google.

    The mobile app still sends `?native=1` (from when a web client shared
    this endpoint); it is accepted and ignored — every flow is native now.

    Returns:
        302 redirect to Google's consent screen.

    Raises:
        503 if Google OAuth is not configured (missing client id/secret).
    """
    if not google_oauth_service.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google sign-in is not configured on this server.",
        )

    state = google_oauth_service.generate_state()
    auth_url = google_oauth_service.build_authorization_url(state)

    response = RedirectResponse(url=auth_url, status_code=status.HTTP_302_FOUND)
    _set_state_cookie(response, state)
    return response


@router.get("/google/callback")
def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    repo: UserRepository = Depends(_build_repo),
) -> RedirectResponse:
    """
    Receive Google's redirect, verify the state, exchange the code, and
    deep-link the session token back into the mobile app.

    Args:
        code: Authorization code from Google.
        state: State value to be matched against the cookie set in /login.
        error: If present, the user denied consent or Google reported an error.

    Returns:
        302 redirect to overwatch://auth with ?token=<jwt> on success or
        ?auth_error=<code> on failure.
    """
    if error:
        logger.info("Google OAuth callback returned error: %s", error)
        return _finish_auth(error="google_denied")

    if not code or not state:
        return _finish_auth(error="missing_code_or_state")

    expected_state = request.cookies.get(_STATE_COOKIE)
    if not expected_state or expected_state != state:
        logger.warning("OAuth state mismatch — possible CSRF or expired flow")
        return _finish_auth(error="state_mismatch")

    try:
        google_user = google_oauth_service.exchange_code_for_user(code)
    except google_oauth_service.OAuthError:
        logger.exception("Failed to exchange Google OAuth code")
        return _finish_auth(error="oauth_exchange_failed")

    # Email allowlist: if ALLOWED_GOOGLE_EMAILS is set, only those addresses
    # may sign in. Reject before touching the DB so unauthorized signups
    # never create a user row.
    if not is_email_allowed(google_user.email):
        logger.info("Sign-in rejected by allowlist: %s", google_user.email)
        return _finish_auth(error="email_not_allowed")

    # Find or create the user row. google_id is the immutable identifier.
    user = repo.get_by_google_id(google_user.sub)
    if user is None:
        user = repo.create(
            google_id=google_user.sub,
            email=google_user.email,
            name=google_user.name,
            picture=google_user.picture,
        )
        logger.info("Created new user %s (%s)", user.id, user.email)
    else:
        # Refresh profile fields from Google (name and picture can change).
        repo.update_profile(user.id, name=google_user.name, picture=google_user.picture)
        logger.info("Existing user signed in: %s", user.email)

    repo.update_last_login(user.id)

    token = issue_session_token(user.id)
    return _finish_auth(token=token)


@router.get("/me", response_model=UserResponse)
def get_current_user_endpoint(
    authorization: Annotated[str | None, Header()] = None,
    repo: UserRepository = Depends(_build_repo),
) -> UserResponse:
    """
    Return the current signed-in user, or 401.

    Returns:
        UserResponse on success.

    Raises:
        401 if the token is missing, expired, or invalid.
    """
    user = _user_from_token(_bearer_token(authorization), repo)
    repo.update_last_login(user.id)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout() -> None:
    """
    Acknowledge sign-out. Sessions are stateless bearer JWTs, so there is
    nothing to clear server-side — the app deletes its stored token.
    Kept as an endpoint so the client has a stable hook if server-side
    revocation is ever added.
    """


# ---------------------------------------------------------------------------
# FastAPI dependency for auth-gating other routes
# ---------------------------------------------------------------------------


def current_user(
    authorization: Annotated[str | None, Header()] = None,
    repo: UserRepository = Depends(_build_repo),
) -> UserResponse:
    """
    FastAPI dependency that materializes the signed-in user, or 401s.

    Reads `Authorization: Bearer <token>`. This is the single auth
    chokepoint every protected route depends on.

    Use in routes:
        @router.get("/commitments")
        def list_commitments(user: UserResponse = Depends(current_user)):
            ...

    Returns:
        UserResponse for the signed-in user.

    Raises:
        401 if the token is missing, invalid, or the user no longer exists.
    """
    return _user_from_token(_bearer_token(authorization), repo)


# ---------------------------------------------------------------------------
# OAuth state cookie + redirect helpers
# ---------------------------------------------------------------------------


def _secure_cookies() -> bool:
    """Return True if cookies should carry the Secure flag (HTTPS only)."""
    return settings.environment == "production"


def _set_state_cookie(response: RedirectResponse, state: str) -> None:
    """
    Apply the short-lived OAuth state cookie.

    SameSite=Lax is enough: the cookie only has to survive the top-level
    GET navigation Google → /auth/google/callback inside the system browser.
    """
    response.set_cookie(
        key=_STATE_COOKIE,
        value=state,
        max_age=_STATE_COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        secure=_secure_cookies(),
        samesite="lax",
        path="/",
    )


def _finish_auth(token: str | None = None, error: str | None = None) -> RedirectResponse:
    """
    Finalize the OAuth callback: deep-link the result into the mobile app.

    On success: overwatch://auth?token=<jwt> — the app captures the token
    from the auth session result and stores it in secure storage.
    On failure: overwatch://auth?auth_error=<code>.
    The OAuth state cookie is cleared either way.

    Args:
        token: The freshly-issued session JWT on success.
        error: An error code on failure (mutually exclusive with token).

    Returns:
        302 redirect to the app's custom URL scheme.
    """
    if token:
        url = f"{_NATIVE_REDIRECT_SCHEME}://auth?token={token}"
    else:
        url = f"{_NATIVE_REDIRECT_SCHEME}://auth?auth_error={error or 'sign_in_failed'}"
    response = RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)
    response.delete_cookie(
        key=_STATE_COOKIE,
        path="/",
        secure=_secure_cookies(),
        httponly=True,
        samesite="lax",
    )
    return response
