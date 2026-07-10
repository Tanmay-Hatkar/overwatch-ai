"""
test_reflection_routes.py — Integration tests for /reflections endpoints.

Mirrors test_briefing_routes.py. We mock call_llm at the reflection_service
module level (same place the unit tests mock it). The route + service +
repository + DB chain runs for real otherwise.
"""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.repositories.user_repository import UserRepository
from app.services.jwt_service import issue_session_token

LLM_PATCH_TARGET = "app.services.reflection_service.call_llm"


def test_get_today_returns_reflection(authed_client: TestClient) -> None:
    """Happy path: GET /reflections/today returns 200 with the reflection body."""
    with patch(LLM_PATCH_TARGET, return_value="Good evening. Quiet day."):
        response = authed_client.get("/reflections/today")

    assert response.status_code == 200
    body = response.json()
    assert body["content"] == "Good evening. Quiet day."
    assert body["done_count"] == 0
    assert body["open_count"] == 0
    assert body["abandoned_count"] == 0
    assert "generated_at" in body


def test_get_today_returns_503_when_llm_unavailable(authed_client: TestClient) -> None:
    """When the LLM returns None, /reflections/today returns 503."""
    with patch(LLM_PATCH_TARGET, return_value=None):
        response = authed_client.get("/reflections/today")
    assert response.status_code == 503


def test_get_today_includes_commitment_counts(authed_client: TestClient) -> None:
    """Counts in the response reflect commitments in the database."""
    created = authed_client.post(
        "/commitments", json={"text": "Today's task", "due_at": None}
    ).json()
    authed_client.patch(f"/commitments/{created['id']}", json={"status": "done"})

    with patch(LLM_PATCH_TARGET, return_value="reflection"):
        response = authed_client.get("/reflections/today")

    assert response.status_code == 200
    assert response.json()["done_count"] == 1


def test_second_call_is_cached(authed_client: TestClient) -> None:
    """A second call with no commitment changes returns the cache (cached=true)."""
    with patch(LLM_PATCH_TARGET, return_value="First.") as mock:
        first = authed_client.get("/reflections/today")
        second = authed_client.get("/reflections/today")

    assert first.json()["cached"] is False
    assert second.json()["cached"] is True
    assert mock.call_count == 1


def test_force_regenerate_bypasses_cache(authed_client: TestClient) -> None:
    """?force_regenerate=true always calls the LLM, even with a fresh cache."""
    with patch(LLM_PATCH_TARGET, return_value="First.") as mock:
        authed_client.get("/reflections/today")
        authed_client.get("/reflections/today?force_regenerate=true")

    assert mock.call_count == 2


def test_reflection_is_scoped_to_the_signed_in_user(db_connection, test_user) -> None:
    """
    User A's reflection isn't visible to user B, even for the same date —
    every read/write is scoped by user_id (ADR-0013's multi-tenancy pattern).
    """

    def _override_get_db():
        yield db_connection

    app.dependency_overrides[get_db] = _override_get_db
    try:
        client_a = TestClient(app)
        client_a.cookies.set("ow_session", issue_session_token(test_user.id))

        user_b = UserRepository(db_connection).create(
            google_id="g-other", email="other@example.com", name="Other User", picture=None
        )
        client_b = TestClient(app)
        client_b.cookies.set("ow_session", issue_session_token(user_b.id))

        with patch(LLM_PATCH_TARGET, return_value="User A's reflection."):
            response_a = client_a.get("/reflections/today")
        assert response_a.status_code == 200
        assert response_a.json()["content"] == "User A's reflection."

        with patch(LLM_PATCH_TARGET, return_value="User B's reflection.") as mock_b:
            response_b = client_b.get("/reflections/today")
        assert response_b.status_code == 200
        assert response_b.json()["content"] == "User B's reflection."
        # User B got a FRESH generation (own LLM call), not user A's cached one.
        mock_b.assert_called_once()
    finally:
        app.dependency_overrides.clear()
