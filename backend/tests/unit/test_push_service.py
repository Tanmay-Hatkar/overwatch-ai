"""
test_push_service.py — Unit tests for PushService.

Mocks `webpush` at the import site so no real HTTP calls happen.
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from pywebpush import WebPushException

from app.models.push import PushSubscriptionResponse
from app.services.push_service import PushPayload, PushService

WEBPUSH_TARGET = "app.services.push_service.webpush"


def _make_subscription(endpoint="https://push.example/a") -> PushSubscriptionResponse:
    return PushSubscriptionResponse(
        id=uuid4(),
        endpoint=endpoint,
        p256dh="p256",
        auth="auth",
        created_at=datetime.now(UTC),
    )


def _make_service() -> PushService:
    return PushService(vapid_private_key="fake-key", vapid_subject="mailto:test@example.com")


# ---------------------------------------------------------------------------
# is_configured
# ---------------------------------------------------------------------------


def test_is_configured_true_when_key_set() -> None:
    assert _make_service().is_configured is True


def test_is_configured_false_when_key_empty(monkeypatch) -> None:
    """Empty constructor arg AND empty settings fallback → not configured."""
    monkeypatch.setattr("app.services.push_service.settings.vapid_private_key", "")
    service = PushService(vapid_private_key="", vapid_subject="mailto:test@example.com")
    assert service.is_configured is False


def test_send_returns_false_when_not_configured(monkeypatch) -> None:
    """Without a VAPID key, send is a no-op returning (False, False)."""
    monkeypatch.setattr("app.services.push_service.settings.vapid_private_key", "")
    service = PushService(vapid_private_key="", vapid_subject="mailto:t@e.com")
    delivered, stale = service.send(_make_subscription(), PushPayload("T", "B"))
    assert delivered is False
    assert stale is False


# ---------------------------------------------------------------------------
# send (success and failure paths)
# ---------------------------------------------------------------------------


def test_send_success_calls_webpush_with_correct_payload() -> None:
    service = _make_service()
    sub = _make_subscription()
    payload = PushPayload(title="Hi", body="There", tag="commitment-1")

    with patch(WEBPUSH_TARGET) as mock_webpush:
        delivered, stale = service.send(sub, payload)

    assert delivered is True
    assert stale is False
    mock_webpush.assert_called_once()
    # Verify the data sent to webpush is our JSON-encoded payload
    kwargs = mock_webpush.call_args.kwargs
    assert kwargs["vapid_private_key"] == "fake-key"
    assert '"title": "Hi"' in kwargs["data"]
    assert '"body": "There"' in kwargs["data"]


def test_send_410_marks_subscription_stale() -> None:
    """HTTP 410 from the push service means the subscription is gone."""
    service = _make_service()
    sub = _make_subscription()

    fake_response = MagicMock()
    fake_response.status_code = 410
    exc = WebPushException("gone", response=fake_response)

    with patch(WEBPUSH_TARGET, side_effect=exc):
        delivered, stale = service.send(sub, PushPayload("T", "B"))

    assert delivered is False
    assert stale is True


def test_send_404_marks_subscription_stale() -> None:
    service = _make_service()
    fake_response = MagicMock()
    fake_response.status_code = 404
    exc = WebPushException("not found", response=fake_response)

    with patch(WEBPUSH_TARGET, side_effect=exc):
        _, stale = service.send(_make_subscription(), PushPayload("T", "B"))
    assert stale is True


def test_send_other_error_returns_false_false() -> None:
    """Non-gone errors are logged but don't mark the subscription stale."""
    service = _make_service()
    fake_response = MagicMock()
    fake_response.status_code = 500
    exc = WebPushException("server error", response=fake_response)

    with patch(WEBPUSH_TARGET, side_effect=exc):
        delivered, stale = service.send(_make_subscription(), PushPayload("T", "B"))
    assert delivered is False
    assert stale is False


def test_send_unexpected_exception_returns_false_false() -> None:
    """A non-WebPushException (e.g., network error) is also handled."""
    service = _make_service()
    with patch(WEBPUSH_TARGET, side_effect=RuntimeError("connection refused")):
        delivered, stale = service.send(_make_subscription(), PushPayload("T", "B"))
    assert delivered is False
    assert stale is False


# ---------------------------------------------------------------------------
# broadcast
# ---------------------------------------------------------------------------


def test_broadcast_returns_only_stale_endpoints() -> None:
    """broadcast collects endpoints of stale subscriptions; healthy ones omitted."""
    service = _make_service()
    healthy = _make_subscription(endpoint="https://ok/")
    stale_sub = _make_subscription(endpoint="https://gone/")

    # Patch send() to simulate one stale + one healthy
    def fake_send(sub, _payload):
        return (True, False) if sub.endpoint == "https://ok/" else (False, True)

    with patch.object(service, "send", side_effect=fake_send):
        stale = service.broadcast([healthy, stale_sub], PushPayload("T", "B"))

    assert stale == ["https://gone/"]
