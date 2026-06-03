"""
test_push_subscription_repository.py — Unit tests for PushSubscriptionRepository.

Real in-memory SQLite database via the `db_connection` fixture.
"""

import pytest

from app.repositories.push_subscription_repository import PushSubscriptionRepository


@pytest.fixture
def repo(db_connection) -> PushSubscriptionRepository:
    return PushSubscriptionRepository(db_connection)


def test_upsert_inserts_new_subscription(repo: PushSubscriptionRepository) -> None:
    sub = repo.upsert(endpoint="https://push.example/a", p256dh="key1", auth="auth1")
    assert sub.endpoint == "https://push.example/a"
    assert sub.p256dh == "key1"
    assert sub.auth == "auth1"


def test_upsert_replaces_existing_keys(repo: PushSubscriptionRepository) -> None:
    """Re-subscribing from the same browser updates keys rather than duplicating."""
    first = repo.upsert(endpoint="https://push.example/a", p256dh="old", auth="old-auth")
    second = repo.upsert(endpoint="https://push.example/a", p256dh="new", auth="new-auth")

    # Same id (same row)
    assert second.id == first.id
    # Keys refreshed
    assert second.p256dh == "new"
    assert second.auth == "new-auth"


def test_list_all_returns_all_subscriptions(repo: PushSubscriptionRepository) -> None:
    repo.upsert(endpoint="https://a/", p256dh="k", auth="a")
    repo.upsert(endpoint="https://b/", p256dh="k", auth="a")
    repo.upsert(endpoint="https://c/", p256dh="k", auth="a")
    assert len(repo.list_all()) == 3


def test_list_all_empty_database(repo: PushSubscriptionRepository) -> None:
    assert repo.list_all() == []


def test_delete_by_endpoint_returns_true_when_existing(repo: PushSubscriptionRepository) -> None:
    repo.upsert(endpoint="https://push.example/a", p256dh="k", auth="a")
    assert repo.delete_by_endpoint("https://push.example/a") is True
    assert repo.list_all() == []


def test_delete_by_endpoint_returns_false_when_missing(repo: PushSubscriptionRepository) -> None:
    assert repo.delete_by_endpoint("https://nonexistent/") is False
