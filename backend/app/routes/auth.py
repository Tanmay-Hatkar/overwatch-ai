"""
auth.py — Authentication routes (Google OAuth + session management).

Endpoints:
  GET  /auth/google/login      Redirect to Google's consent screen
  GET  /auth/google/callback   Receive code from Google, mint session cookie
  GET  /auth/me                Return the current user, refreshing the cookie
                               if it's near expiry. 401 if not signed in.
  POST /auth/logout            Clear the session cookie.

All four endpoints set/clear cookies directly on the response. The actual
identity work is done by the JWT and Google OAuth services — these
routes are HTTP glue.

The current_user FastAPI dependency lives at the bottom of this module
and is imported by other routes for auth-gating.
"""

import logging
import sqlite3
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse, Response

from app.config import settings
from app.database import get_db
from app.models.user import UserResponse
from app.repositories.user_repository import UserRepository
from app.services import google_oauth_service
from app.services.jwt_service import (
    JWTError,
    issue_session_token,
    should_refresh,
    verify_session_token,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# Short-lived cookie name carrying the OAuth `state` between /login and
# /callback. Used solely for CSRF protection on the OAuth flow.
_STATE_COOKIE = "ow_oauth_state"
_STATE_COOKIE_MAX_AGE_SECONDS = 600  # 10 minutes


def _build_repo(conn: sqlite3.Connection = Depends(get_db)) -> UserRepository:
    """FastAPI dependency that wires a UserRepository to the request's DB connection."""
    return UserRepository(conn)


@router.get("/google/login")
def google_login() -> RedirectResponse:
    """
    Start the OAuth flow. Sets a short-lived state cookie and 302s to Google.

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
    Receive Google's redirect, verify the state, exchange the code, set the
    session cookie, and redirect to the frontend.

    Args:
        code: Authorization code from Google.
        state: State value to be matched against the cookie set in /login.
        error: If present, the user denied consent or Google reported an error.

    Returns:
        302 redirect to the frontend (with the session cookie set on success,
        or with a query string error parameter on failure).
    """
    if error:
        logger.info("Google OAuth callback returned error: %s", error)
        return _redirect_to_frontend(error="google_denied")

    if not code or not state:
        return _redirect_to_frontend(error="missing_code_or_state")

    expected_state = request.cookies.get(_STATE_COOKIE)
    if not expected_state or expected_state != state:
        logger.warning("OAuth state mismatch — possible CSRF or expired flow")
        return _redirect_to_frontend(error="state_mismatch")

    try:
        google_user = google_oauth_service.exchange_code_for_user(code)
    except google_oauth_service.OAuthError:
        logger.exception("Failed to exchange Google OAuth code")
        return _redirect_to_frontend(error="oauth_exchange_failed")

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
    response = _redirect_to_frontend()
    _clear_state_cookie(response)
    _set_session_cookie(response, token)
    return response


@router.get("/me", response_model=UserResponse)
def get_current_user_endpoint(
    response: Response,
    session: Annotated[str | None, Cookie(alias="ow_session")] = None,
    repo: UserRepository = Depends(_build_repo),
) -> UserResponse:
    """
    Return the current signed-in user, or 401.

    Side effect: if the cookie's JWT is within the refresh window
    (settings.session_refresh_within_days of expiry), this endpoint
    silently re-issues a fresh cookie. The user never sees a forced
    logout as long as they keep using the app.

    Args:
        session: The JWT from the ow_session cookie.

    Returns:
        UserResponse on success.

    Raises:
        401 if the cookie is missing, expired, or invalid.
    """
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not signed in")

    try:
        user_id = verify_session_token(session)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session invalid or expired",
        ) from exc

    user = repo.get_by_id(user_id)
    if user is None:
        # User row was deleted but their cookie is still floating around.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists",
        )

    repo.update_last_login(user.id)

    if should_refresh(session):
        new_token = issue_session_token(user.id)
        _set_session_cookie(response, new_token)
        logger.debug("Refreshed session cookie for user %s", user.id)

    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    """
    Clear the session cookie. Idempotent — calling when already signed
    out is fine.
    """
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        secure=_secure_cookies(),
        httponly=True,
        samesite="lax",
    )


# ---------------------------------------------------------------------------
# FastAPI dependency for auth-gating other routes
# ---------------------------------------------------------------------------


def current_user(
    session: Annotated[str | None, Cookie(alias="ow_session")] = None,
    repo: UserRepository = Depends(_build_repo),
) -> UserResponse:
    """
    FastAPI dependency that materializes the signed-in user, or 401s.

    Use in routes:
        @router.get("/commitments")
        def list_commitments(user: UserResponse = Depends(current_user)):
            ...

    Args:
        session: The JWT from the ow_session cookie (auto-injected by FastAPI).

    Returns:
        UserResponse for the signed-in user.

    Raises:
        401 if the session is missing, invalid, or the user no longer exists.
    """
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not signed in")
    try:
        user_id = verify_session_token(session)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session invalid or expired",
        ) from exc

    user = repo.get_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists",
        )
    return user


# ---------------------------------------------------------------------------
# Cookie helpers
# ---------------------------------------------------------------------------


def _secure_cookies() -> bool:
    """Return True if cookies should carry the Secure flag (HTTPS only)."""
    return settings.environment == "production"


def _set_session_cookie(response: Response, token: str) -> None:
    """Apply the standard session cookie attributes."""
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_max_age_days * 24 * 60 * 60,
        httponly=True,
        secure=_secure_cookies(),
        samesite="lax",
        path="/",
    )


def _set_state_cookie(response: Response, state: str) -> None:
    """Apply the short-lived OAuth state cookie."""
    response.set_cookie(
        key=_STATE_COOKIE,
        value=state,
        max_age=_STATE_COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        secure=_secure_cookies(),
        samesite="lax",
        path="/",
    )


def _clear_state_cookie(response: Response) -> None:
    """Wipe the OAuth state cookie after the callback succeeds."""
    response.delete_cookie(
        key=_STATE_COOKIE,
        path="/",
        secure=_secure_cookies(),
        httponly=True,
        samesite="lax",
    )


def _redirect_to_frontend(error: str | None = None) -> RedirectResponse:
    """
    Build the post-callback redirect back to the frontend.

    On success: redirect to settings.frontend_url (root). The browser
    sees the new session cookie and the frontend's auth check succeeds.

    On failure: append ?auth_error=<code> so the frontend can show a
    friendly message.
    """
    base = settings.frontend_url.rstrip("/")
    url = f"{base}/?auth_error={error}" if error else f"{base}/"
    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)
