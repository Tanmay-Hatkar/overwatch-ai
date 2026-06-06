"""
test_google_oauth_service.py — Unit tests for the Google OAuth flow service.

Covers:
  - is_configured() reflects settings state
  - generate_state() produces unique values
  - build_authorization_url() embeds expected params and raises if unconfigured
  - exchange_code_for_user() success path (verified id_token)
  - exchange_code_for_user() failure paths (network error, bad code, unverified email)
"""

from unittest.mock import MagicMock, patch

import pytest
import requests

from app.services import google_oauth_service
from app.services.google_oauth_service import OAuthError


@pytest.fixture(autouse=True)
def _configure_oauth(monkeypatch: pytest.MonkeyPatch) -> None:
    """All tests get a valid-looking OAuth config unless they override."""
    monkeypatch.setattr(
        "app.services.google_oauth_service.settings.google_client_id",
        "test-client-id.apps.googleusercontent.com",
    )
    monkeypatch.setattr(
        "app.services.google_oauth_service.settings.google_client_secret",
        "test-client-secret",
    )
    monkeypatch.setattr(
        "app.services.google_oauth_service.settings.backend_url",
        "http://localhost:8000",
    )


def test_is_configured_true_when_credentials_present() -> None:
    assert google_oauth_service.is_configured() is True


def test_is_configured_false_when_client_id_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.google_oauth_service.settings.google_client_id", ""
    )
    assert google_oauth_service.is_configured() is False


def test_generate_state_returns_unique_values() -> None:
    """Different calls produce different states (cryptographic randomness)."""
    assert google_oauth_service.generate_state() != google_oauth_service.generate_state()


def test_generate_state_is_reasonably_long() -> None:
    """At least 32 chars of url-safe base64 (~256 bits of entropy)."""
    assert len(google_oauth_service.generate_state()) >= 32


def test_build_authorization_url_includes_required_params() -> None:
    url = google_oauth_service.build_authorization_url("state-xyz")
    assert "client_id=test-client-id.apps.googleusercontent.com" in url
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A8000%2Fauth%2Fgoogle%2Fcallback" in url
    assert "state=state-xyz" in url
    assert "scope=openid+email+profile" in url
    assert "response_type=code" in url
    assert url.startswith("https://accounts.google.com/")


def test_build_authorization_url_raises_when_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.google_oauth_service.settings.google_client_id", ""
    )
    with pytest.raises(OAuthError):
        google_oauth_service.build_authorization_url("any-state")


def test_exchange_code_for_user_success() -> None:
    """Happy path: token exchange returns id_token, verification yields user."""
    mock_response = MagicMock()
    mock_response.ok = True
    mock_response.json.return_value = {"id_token": "fake.id.token"}

    verified_payload = {
        "sub": "google-sub-123",
        "email": "alice@example.com",
        "name": "Alice",
        "picture": "https://example.com/alice.png",
        "email_verified": True,
    }

    with (
        patch("app.services.google_oauth_service.requests.post", return_value=mock_response),
        patch(
            "app.services.google_oauth_service.google_id_token.verify_oauth2_token",
            return_value=verified_payload,
        ),
    ):
        user = google_oauth_service.exchange_code_for_user("test-code")

    assert user.sub == "google-sub-123"
    assert user.email == "alice@example.com"
    assert user.name == "Alice"
    assert user.picture == "https://example.com/alice.png"


def test_exchange_code_for_user_rejects_unverified_email() -> None:
    """Google sometimes returns email_verified=False — refuse those sign-ins."""
    mock_response = MagicMock()
    mock_response.ok = True
    mock_response.json.return_value = {"id_token": "fake.id.token"}

    with (
        patch("app.services.google_oauth_service.requests.post", return_value=mock_response),
        patch(
            "app.services.google_oauth_service.google_id_token.verify_oauth2_token",
            return_value={
                "sub": "g",
                "email": "x@example.com",
                "name": "X",
                "email_verified": False,
            },
        ),
        pytest.raises(OAuthError, match="not verified"),
    ):
        google_oauth_service.exchange_code_for_user("test-code")


def test_exchange_code_for_user_handles_token_endpoint_error() -> None:
    """Non-2xx from Google's token endpoint raises OAuthError."""
    mock_response = MagicMock()
    mock_response.ok = False
    mock_response.status_code = 400
    mock_response.text = "invalid_grant"

    with (
        patch("app.services.google_oauth_service.requests.post", return_value=mock_response),
        pytest.raises(OAuthError, match="rejected"),
    ):
        google_oauth_service.exchange_code_for_user("bad-code")


def test_exchange_code_for_user_handles_network_error() -> None:
    """RequestException becomes OAuthError, not a 500."""
    with (
        patch(
            "app.services.google_oauth_service.requests.post",
            side_effect=requests.ConnectionError("network down"),
        ),
        pytest.raises(OAuthError, match="Network error"),
    ):
        google_oauth_service.exchange_code_for_user("any-code")


def test_exchange_code_for_user_rejects_missing_id_token() -> None:
    """If Google's response somehow lacks id_token, raise rather than crash."""
    mock_response = MagicMock()
    mock_response.ok = True
    mock_response.json.return_value = {"access_token": "only-access"}

    with (
        patch("app.services.google_oauth_service.requests.post", return_value=mock_response),
        pytest.raises(OAuthError, match="id_token"),
    ):
        google_oauth_service.exchange_code_for_user("test-code")


def test_exchange_code_for_user_rejects_unverifiable_id_token() -> None:
    """A signature failure from google-auth becomes OAuthError."""
    mock_response = MagicMock()
    mock_response.ok = True
    mock_response.json.return_value = {"id_token": "tampered"}

    with (
        patch("app.services.google_oauth_service.requests.post", return_value=mock_response),
        patch(
            "app.services.google_oauth_service.google_id_token.verify_oauth2_token",
            side_effect=ValueError("bad signature"),
        ),
        pytest.raises(OAuthError, match="Invalid id_token"),
    ):
        google_oauth_service.exchange_code_for_user("test-code")
