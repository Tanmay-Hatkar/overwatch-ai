"""
test_auth_routes.py — Integration tests for /auth/* endpoints.

Hits the routes via TestClient. The external Google calls are mocked
at the service boundary (google_oauth_service.exchange_code_for_user).
"""

from unittest.mock import patch

import pytest
from app.models.user import GoogleUserInfo
from app.services.jwt_service import issue_session_token, verify_session_token


@pytest.fixture(autouse=True)
def _configure_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test in this module needs a working auth config."""
    monkeypatch.setattr(
        "app.services.jwt_service.settings.session_secret",
        "test-secret-at-least-32-characters-long-for-hs256",
    )
    monkeypatch.setattr(
        "app.routes.auth.settings.session_secret",
        "test-secret-at-least-32-characters-long-for-hs256",
    )
    monkeypatch.setattr(
        "app.services.google_oauth_service.settings.google_client_id",
        "test-client-id.apps.googleusercontent.com",
    )
    monkeypatch.setattr(
        "app.services.google_oauth_service.settings.google_client_secret",
        "test-secret",
    )
    monkeypatch.setattr(
        "app.services.google_oauth_service.settings.backend_url",
        "http://localhost:8000",
    )
    monkeypatch.setattr("app.routes.auth.settings.environment", "development")


def test_google_login_redirects_to_google(client) -> None:
    """GET /auth/google/login returns a 302 to accounts.google.com."""
    response = client.get("/auth/google/login", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"].startswith(
        "https://accounts.google.com/o/oauth2/v2/auth"
    )
    # And sets the state cookie
    assert "ow_oauth_state" in response.cookies


def test_google_login_503_when_not_configured(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """503 if OAuth client credentials are missing."""
    monkeypatch.setattr(
        "app.services.google_oauth_service.settings.google_client_id", ""
    )
    response = client.get("/auth/google/login", follow_redirects=False)
    assert response.status_code == 503


def test_me_returns_401_without_token(client) -> None:
    """No Authorization header → 401."""
    response = client.get("/auth/me")
    assert response.status_code == 401


def test_me_returns_401_with_garbage_token(client) -> None:
    """A non-JWT bearer value is rejected."""
    response = client.get("/auth/me", headers={"Authorization": "Bearer garbage"})
    assert response.status_code == 401


def test_me_ignores_legacy_session_cookie(client, db_connection) -> None:
    """The old web session cookie no longer authenticates — bearer only."""
    from app.repositories.user_repository import UserRepository

    user = UserRepository(db_connection).create("g", "c@example.com", "C", None)
    client.cookies.set("ow_session", issue_session_token(user.id))
    assert client.get("/auth/me").status_code == 401


def test_google_login_accepts_legacy_native_param(client) -> None:
    """The app still sends ?native=1; it must keep working (and is ignored)."""
    response = client.get("/auth/google/login?native=1", follow_redirects=False)
    assert response.status_code == 302


def test_callback_with_state_mismatch_redirects_with_error(client) -> None:
    """CSRF protection: state cookie != state param → error redirect."""
    client.cookies.set("ow_oauth_state", "real-state")
    response = client.get(
        "/auth/google/callback",
        params={"code": "abc", "state": "wrong-state"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["location"] == "overwatch://auth?auth_error=state_mismatch"


def test_callback_with_user_denied_redirects_with_error(client) -> None:
    """Google sometimes returns ?error=access_denied — handle gracefully."""
    response = client.get(
        "/auth/google/callback",
        params={"error": "access_denied"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "auth_error=google_denied" in response.headers["location"]


def _token_from_deep_link(location: str) -> str:
    """Pull the token out of an overwatch://auth?token=<jwt> redirect."""
    prefix = "overwatch://auth?token="
    assert location.startswith(prefix)
    return location[len(prefix):]


def test_callback_success_deep_links_token_and_creates_user(client) -> None:
    """Happy path: callback creates a new user and deep-links a session token."""
    google_user = GoogleUserInfo(
        sub="new-google-sub",
        email="newbie@example.com",
        name="Newbie",
        picture="https://example.com/n.png",
        email_verified=True,
    )

    client.cookies.set("ow_oauth_state", "good-state")
    with patch(
        "app.routes.auth.google_oauth_service.exchange_code_for_user",
        return_value=google_user,
    ):
        response = client.get(
            "/auth/google/callback",
            params={"code": "valid-code", "state": "good-state"},
            follow_redirects=False,
        )

    assert response.status_code == 302
    token = _token_from_deep_link(response.headers["location"])
    assert verify_session_token(token) is not None
    # No session cookie — the token travels in the deep link only
    assert "ow_session" not in response.cookies


def test_callback_returning_user_does_not_duplicate(client, db_connection) -> None:
    """Signing in twice with the same google_id reuses the same user row."""
    from app.repositories.user_repository import UserRepository

    repo = UserRepository(db_connection)
    existing = repo.create(
        google_id="returning-user",
        email="ret@example.com",
        name="Returning",
        picture=None,
    )

    google_user = GoogleUserInfo(
        sub="returning-user",
        email="ret@example.com",
        name="Returning",
        picture=None,
        email_verified=True,
    )

    client.cookies.set("ow_oauth_state", "state-2")
    with patch(
        "app.routes.auth.google_oauth_service.exchange_code_for_user",
        return_value=google_user,
    ):
        response = client.get(
            "/auth/google/callback",
            params={"code": "c", "state": "state-2"},
            follow_redirects=False,
        )

    assert response.status_code == 302
    token = _token_from_deep_link(response.headers["location"])
    assert verify_session_token(token) == existing.id


def test_me_with_valid_token_returns_user(client, db_connection) -> None:
    """A valid bearer token returns the matching user."""
    from app.repositories.user_repository import UserRepository

    repo = UserRepository(db_connection)
    user = repo.create("g", "user@example.com", "User", None)
    token = issue_session_token(user.id)

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "user@example.com"
    assert body["name"] == "User"


def test_me_returns_401_when_user_was_deleted(client) -> None:
    """A token for a nonexistent user is rejected."""
    from uuid import uuid4

    token = issue_session_token(uuid4())
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_logout_returns_204(client) -> None:
    """POST /auth/logout is a stateless acknowledgement — 204, no body."""
    response = client.post("/auth/logout")
    assert response.status_code == 204
    assert response.content == b""
