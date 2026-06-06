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
    monkeypatch.setattr(
        "app.routes.auth.settings.frontend_url", "http://localhost:5173"
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


def test_me_returns_401_without_cookie(client) -> None:
    """No cookie → 401."""
    response = client.get("/auth/me")
    assert response.status_code == 401


def test_me_returns_401_with_garbage_cookie(client) -> None:
    """A non-JWT cookie value is rejected."""
    client.cookies.set("ow_session", "garbage")
    response = client.get("/auth/me")
    assert response.status_code == 401


def test_callback_with_state_mismatch_redirects_with_error(client) -> None:
    """CSRF protection: state cookie != state param → error redirect."""
    client.cookies.set("ow_oauth_state", "real-state")
    response = client.get(
        "/auth/google/callback",
        params={"code": "abc", "state": "wrong-state"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "auth_error=state_mismatch" in response.headers["location"]


def test_callback_with_user_denied_redirects_with_error(client) -> None:
    """Google sometimes returns ?error=access_denied — handle gracefully."""
    response = client.get(
        "/auth/google/callback",
        params={"error": "access_denied"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "auth_error=google_denied" in response.headers["location"]


def test_callback_success_sets_session_cookie_and_creates_user(client) -> None:
    """Happy path: callback creates a new user and sets the session cookie."""
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
    assert response.headers["location"] == "http://localhost:5173/"
    # Session cookie was set
    assert "ow_session" in response.cookies
    # And it's a valid JWT for some user UUID
    token = response.cookies["ow_session"]
    user_id = verify_session_token(token)
    assert user_id is not None


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
    token = response.cookies["ow_session"]
    assert verify_session_token(token) == existing.id


def test_me_with_valid_cookie_returns_user(client, db_connection) -> None:
    """A valid session cookie returns the matching user."""
    from app.repositories.user_repository import UserRepository

    repo = UserRepository(db_connection)
    user = repo.create("g", "user@example.com", "User", None)
    token = issue_session_token(user.id)

    client.cookies.set("ow_session", token)
    response = client.get("/auth/me")
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "user@example.com"
    assert body["name"] == "User"


def test_me_returns_401_when_user_was_deleted(client) -> None:
    """A token for a nonexistent user is rejected."""
    from uuid import uuid4

    token = issue_session_token(uuid4())
    client.cookies.set("ow_session", token)
    response = client.get("/auth/me")
    assert response.status_code == 401


def test_logout_clears_session_cookie(client, db_connection) -> None:
    """POST /auth/logout returns 204 and clears the cookie."""
    from app.repositories.user_repository import UserRepository

    repo = UserRepository(db_connection)
    user = repo.create("g", "out@example.com", "Out", None)
    token = issue_session_token(user.id)

    client.cookies.set("ow_session", token)
    response = client.post("/auth/logout")
    assert response.status_code == 204
    # Set-Cookie should be a delete (max-age=0 or expires in the past)
    set_cookie = response.headers.get("set-cookie", "")
    assert "ow_session=" in set_cookie
    # The cookie value is now empty + an expiry in the past
    assert 'ow_session=""' in set_cookie or "ow_session=;" in set_cookie or "Max-Age=0" in set_cookie
