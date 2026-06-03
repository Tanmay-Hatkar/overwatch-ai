"""
push_service.py — Send Web Push notifications via VAPID.

Wraps pywebpush so callers don't deal with raw HTTP. Handles two
common failure modes:
  - 404/410 ("Gone") — the subscription is stale; the caller can prune it
  - Other errors — logged + swallowed so a single bad subscription
    doesn't block notifications to others

Payload shape: a JSON blob containing the notification title + body.
The service worker on the frontend parses it and calls showNotification().
"""

import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass

from pywebpush import WebPushException, webpush

from app.config import settings
from app.models.push import PushSubscriptionResponse

logger = logging.getLogger(__name__)


@dataclass
class PushPayload:
    """Structured notification content sent to the service worker."""

    title: str
    body: str
    tag: str | None = None  # dedupes notifications with the same tag

    def to_json(self) -> str:
        return json.dumps(
            {"title": self.title, "body": self.body, "tag": self.tag},
            ensure_ascii=False,
        )


class PushService:
    """Sends VAPID-signed Web Push notifications to one or more subscriptions."""

    def __init__(
        self,
        vapid_private_key: str | None = None,
        vapid_subject: str | None = None,
    ) -> None:
        self._private_key = vapid_private_key or settings.vapid_private_key
        self._subject = vapid_subject or settings.vapid_subject

    @property
    def is_configured(self) -> bool:
        """True if we have a VAPID key — required to send pushes."""
        return bool(self._private_key)

    def send(
        self, subscription: PushSubscriptionResponse, payload: PushPayload
    ) -> tuple[bool, bool]:
        """
        Send one push.

        Returns:
            (delivered, stale) — delivered=True on success; stale=True if
            the push service reported the subscription is gone (the caller
            should delete this subscription).
        """
        if not self.is_configured:
            logger.warning("PushService: VAPID private key not configured; skipping send")
            return False, False

        sub_info = {
            "endpoint": subscription.endpoint,
            "keys": {
                "p256dh": subscription.p256dh,
                "auth": subscription.auth,
            },
        }

        try:
            webpush(
                subscription_info=sub_info,
                data=payload.to_json(),
                vapid_private_key=self._private_key,
                vapid_claims={"sub": self._subject},
            )
            return True, False
        except WebPushException as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status in (404, 410):
                logger.info(
                    f"Push subscription stale (HTTP {status}): {subscription.endpoint[:60]}..."
                )
                return False, True
            logger.warning(f"Push send failed: {e}")
            return False, False
        except Exception as e:
            logger.warning(f"Push send unexpected error: {e}")
            return False, False

    def broadcast(
        self,
        subscriptions: Iterable[PushSubscriptionResponse],
        payload: PushPayload,
    ) -> list[str]:
        """
        Send the same payload to many subscriptions.

        Returns:
            List of stale subscription endpoints — caller should delete these.
        """
        stale: list[str] = []
        for sub in subscriptions:
            _delivered, is_stale = self.send(sub, payload)
            if is_stale:
                stale.append(sub.endpoint)
        return stale
