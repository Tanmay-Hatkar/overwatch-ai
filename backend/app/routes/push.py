"""
push.py — FastAPI routes for Web Push notifications.

  GET  /push/vapid-public-key
       Returns the VAPID public key (frontend needs this to subscribe).

  POST /push/subscribe
       Saves a browser subscription so the backend can send it pushes.

  POST /push/unsubscribe
       Removes a stored subscription.

  POST /push/test
       Sends a test push to every stored subscription. Useful for verifying
       the end-to-end pipeline without waiting for a real commitment.
"""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, status

from app.config import settings
from app.database import get_db
from app.models.push import (
    PushSubscriptionCreate,
    PushSubscriptionResponse,
    PushUnsubscribeRequest,
    VapidPublicKeyResponse,
)
from app.models.user import UserResponse
from app.repositories.push_subscription_repository import PushSubscriptionRepository
from app.routes.auth import current_user
from app.services.push_service import PushPayload, PushService
from app.services.vapid_keys import derive_vapid_public_key

router = APIRouter(prefix="/push", tags=["push"])

# Single PushService instance — stateless, no per-request setup
_push_service = PushService()


def _build_repo(conn: sqlite3.Connection = Depends(get_db)) -> PushSubscriptionRepository:
    return PushSubscriptionRepository(conn)


def get_push_service() -> PushService:
    """FastAPI dependency returning the singleton PushService."""
    return _push_service


@router.get("/vapid-public-key", response_model=VapidPublicKeyResponse)
def get_vapid_public_key() -> VapidPublicKeyResponse:
    """
    Return the VAPID public key for the frontend to subscribe with.

    The key is DERIVED from the private key (the single source of truth), so
    it's always guaranteed to match — no separate VAPID_PUBLIC_KEY to keep in
    sync. If no private key is configured, fall back to an explicitly-set
    public key, else 503.
    """
    key = derive_vapid_public_key(settings.vapid_private_key) or settings.vapid_public_key
    if not key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="VAPID is not configured on the server.",
        )
    return VapidPublicKeyResponse(public_key=key)


@router.post(
    "/subscribe",
    response_model=PushSubscriptionResponse,
    status_code=status.HTTP_201_CREATED,
)
def subscribe(
    payload: PushSubscriptionCreate,
    user: UserResponse = Depends(current_user),
    repo: PushSubscriptionRepository = Depends(_build_repo),
) -> PushSubscriptionResponse:
    """Register the signed-in user's browser subscription. Idempotent by endpoint."""
    return repo.upsert(
        user.id,
        endpoint=payload.endpoint,
        p256dh=payload.keys.p256dh,
        auth=payload.keys.auth,
    )


@router.post("/unsubscribe", status_code=status.HTTP_204_NO_CONTENT)
def unsubscribe(
    payload: PushUnsubscribeRequest,
    user: UserResponse = Depends(current_user),
    repo: PushSubscriptionRepository = Depends(_build_repo),
) -> None:
    """Remove a stored subscription by endpoint. 204 either way."""
    repo.delete_by_endpoint(payload.endpoint)


@router.post("/test", status_code=status.HTTP_200_OK)
def send_test_push(
    user: UserResponse = Depends(current_user),
    repo: PushSubscriptionRepository = Depends(_build_repo),
    push_service: PushService = Depends(get_push_service),
) -> dict[str, int]:
    """
    Broadcast a test push to the signed-in user's devices. Useful for manual
    verification that the push pipeline works end-to-end.

    Returns counts for delivered vs stale subscriptions. Stale ones are
    automatically pruned.
    """
    if not push_service.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="VAPID_PRIVATE_KEY is not configured on the server.",
        )

    subscriptions = repo.list_for_user(user.id)
    payload = PushPayload(
        title="Overwatch",
        body="Test push — your reminders are working.",
        tag="test",
    )
    stale = push_service.broadcast(subscriptions, payload)

    # Prune stale subscriptions
    for endpoint in stale:
        repo.delete_by_endpoint(endpoint)

    return {
        "total": len(subscriptions),
        "stale_pruned": len(stale),
        "delivered": len(subscriptions) - len(stale),
    }
