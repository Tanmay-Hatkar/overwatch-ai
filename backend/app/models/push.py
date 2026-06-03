"""
push.py — Pydantic schemas for Web Push subscriptions.

A PushSubscription is the per-device handle the browser gives us when
the user grants notification permission. We store these in the database
and use them to send notifications when commitments become due.

Fields per the Web Push spec:
  - endpoint:  URL the push service will deliver to (browser-vendor-specific)
  - p256dh:    browser-generated public key for encrypting payloads
  - auth:      browser-generated auth secret used in the encryption
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PushSubscriptionKeys(BaseModel):
    """Browser-supplied encryption keys for a push subscription."""

    p256dh: str = Field(..., min_length=1, description="P-256 ECDH public key (base64url)")
    auth: str = Field(..., min_length=1, description="Auth secret (base64url)")


class PushSubscriptionCreate(BaseModel):
    """Request body for POST /push/subscribe."""

    endpoint: str = Field(..., min_length=1, description="Push service endpoint URL")
    keys: PushSubscriptionKeys = Field(..., description="Browser-supplied keys")


class PushSubscriptionResponse(BaseModel):
    """Response body for any endpoint returning a subscription."""

    id: UUID
    endpoint: str
    p256dh: str
    auth: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VapidPublicKeyResponse(BaseModel):
    """Response body for GET /push/vapid-public-key."""

    public_key: str = Field(..., description="VAPID public key (base64url) for the frontend")


class PushUnsubscribeRequest(BaseModel):
    """Request body for POST /push/unsubscribe."""

    endpoint: str = Field(..., min_length=1)
