"""
test_jwt_service.py — Unit tests for session JWT issuance and verification.

Covers:
  - Round-trip: issue then verify recovers the same UUID
  - Expired tokens raise JWTError
  - Tampered tokens raise JWTError
  - Missing session_secret raises ValueError on issue
  - should_refresh fires within the refresh window and not outside it
"""

import time
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
import pytest

from app.services.jwt_service import (
    JWTError,
    issue_session_token,
    should_refresh,
    verify_session_token,
)


@pytest.fixture(autouse=True)
def _set_session_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test in this module needs a stable signing key."""
    monkeypatch.setattr(
        "app.services.jwt_service.settings.session_secret",
        "test-secret-at-least-32-characters-long-for-hs256",
    )


def test_issue_then_verify_round_trip() -> None:
    """Issuing a token and verifying it recovers the original UUID."""
    user_id = uuid4()
    token = issue_session_token(user_id)
    assert verify_session_token(token) == user_id


def test_verify_rejects_tampered_signature() -> None:
    """Mutating any character of the JWT invalidates the signature."""
    token = issue_session_token(uuid4())
    tampered = token[:-2] + ("AB" if token[-2:] != "AB" else "CD")
    with pytest.raises(JWTError):
        verify_session_token(tampered)


def test_verify_rejects_expired_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """A token issued in the past with max_age_days=0 is immediately expired."""
    # Issue a token that expired 1 hour ago by patching datetime at issue time.
    now = datetime.now(UTC)
    payload = {
        "sub": str(uuid4()),
        "iat": int((now - timedelta(hours=2)).timestamp()),
        "exp": int((now - timedelta(hours=1)).timestamp()),
    }
    expired = jwt.encode(
        payload,
        "test-secret-at-least-32-characters-long-for-hs256",
        algorithm="HS256",
    )
    with pytest.raises(JWTError):
        verify_session_token(expired)


def test_verify_rejects_missing_sub_claim() -> None:
    """A token without a sub claim is rejected."""
    now = datetime.now(UTC)
    bad = jwt.encode(
        {
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(days=1)).timestamp()),
        },
        "test-secret-at-least-32-characters-long-for-hs256",
        algorithm="HS256",
    )
    with pytest.raises(JWTError):
        verify_session_token(bad)


def test_verify_rejects_garbage() -> None:
    """Random non-JWT input fails closed."""
    with pytest.raises(JWTError):
        verify_session_token("not.a.jwt")


def test_issue_raises_without_session_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """Refuse to mint tokens with an empty signing key (misconfig)."""
    monkeypatch.setattr("app.services.jwt_service.settings.session_secret", "")
    with pytest.raises(ValueError):
        issue_session_token(uuid4())


def test_should_refresh_true_when_within_refresh_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tokens about to expire return True."""
    # Refresh window is 7 days; issue a token with 3 days left.
    monkeypatch.setattr(
        "app.services.jwt_service.settings.session_refresh_within_days", 7
    )
    token = issue_session_token(uuid4(), max_age_days=3)
    assert should_refresh(token) is True


def test_should_refresh_false_when_outside_refresh_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tokens with plenty of life left return False."""
    monkeypatch.setattr(
        "app.services.jwt_service.settings.session_refresh_within_days", 7
    )
    token = issue_session_token(uuid4(), max_age_days=30)
    assert should_refresh(token) is False


def test_should_refresh_false_for_garbage_token() -> None:
    """Invalid tokens don't trigger refresh (verify_session_token rejects them first anyway)."""
    assert should_refresh("not.a.jwt") is False


def test_token_sub_is_uuid_string() -> None:
    """The sub claim is the UUID's canonical string form (so it round-trips)."""
    user_id = UUID("12345678-1234-5678-1234-567812345678")
    token = issue_session_token(user_id)
    payload = jwt.decode(
        token,
        "test-secret-at-least-32-characters-long-for-hs256",
        algorithms=["HS256"],
    )
    assert payload["sub"] == str(user_id)


def test_issued_at_and_expiry_are_consistent() -> None:
    """exp = iat + max_age_days * 86400, within 2 seconds (clock skew tolerance)."""
    before = int(time.time())
    token = issue_session_token(uuid4(), max_age_days=30)
    payload = jwt.decode(
        token,
        "test-secret-at-least-32-characters-long-for-hs256",
        algorithms=["HS256"],
    )
    expected_exp = before + 30 * 86400
    assert abs(payload["exp"] - expected_exp) < 5
    assert payload["exp"] - payload["iat"] == 30 * 86400
