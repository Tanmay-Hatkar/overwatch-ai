"""
test_briefing_routes.py — Integration tests for /briefings endpoints.

We mock call_llm at the briefing_service module level (same place the
unit tests mock it). The route + service + repository + DB chain runs
for real otherwise.
"""

from datetime import UTC, datetime
from unittest.mock import patch

from fastapi.testclient import TestClient

LLM_PATCH_TARGET = "app.services.briefing_service.call_llm"


def test_get_today_returns_briefing(authed_client: TestClient) -> None:
    """Happy path: GET /briefings/today returns 200 with the briefing body."""
    with patch(LLM_PATCH_TARGET, return_value="Good morning. Test briefing."):
        response = authed_client.get("/briefings/today")

    assert response.status_code == 200
    body = response.json()
    assert body["content"] == "Good morning. Test briefing."
    assert body["today_count"] == 0
    assert body["overdue_count"] == 0
    assert "generated_at" in body


def test_get_today_returns_503_when_llm_unavailable(authed_client: TestClient) -> None:
    """When the LLM returns None, /briefings/today returns 503."""
    with patch(LLM_PATCH_TARGET, return_value=None):
        response = authed_client.get("/briefings/today")
    assert response.status_code == 503


def test_get_today_includes_commitment_counts(authed_client: TestClient) -> None:
    """Counts in the response match commitments in the database."""
    # UTC-anchored, not server-local: /briefings/today defaults to UTC when
    # no ?timezone= is passed (as here), so the fixture must agree with that
    # reference clock or it silently mismatches on a non-UTC machine.
    today_noon = datetime.combine(datetime.now(UTC).date(), datetime.min.time().replace(hour=12), tzinfo=UTC)
    authed_client.post(
        "/commitments",
        json={"text": "Today's task", "due_at": today_noon.isoformat()},
    )

    with patch(LLM_PATCH_TARGET, return_value="briefing"):
        response = authed_client.get("/briefings/today")

    assert response.status_code == 200
    assert response.json()["today_count"] == 1
