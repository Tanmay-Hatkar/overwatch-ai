"""
test_stats_routes.py — Integration tests for /stats endpoints.
"""

from fastapi.testclient import TestClient


def test_get_today_returns_zeros_on_empty_db(authed_client: TestClient) -> None:
    """With no commitments, /stats/today returns all zeros and 7 daily entries."""
    response = authed_client.get("/stats/today")
    assert response.status_code == 200
    body = response.json()
    assert body["completed_today"] == 0
    assert body["completed_this_week"] == 0
    assert body["streak_days"] == 0
    assert len(body["daily_completions"]) == 7


def test_get_today_reflects_completed_commitment(authed_client: TestClient) -> None:
    """After completing a commitment via PATCH, the stats reflect it."""
    # Create + complete
    created = authed_client.post(
        "/commitments", json={"text": "Done task", "due_at": None}
    ).json()
    authed_client.patch(f"/commitments/{created['id']}", json={"status": "done"})

    response = authed_client.get("/stats/today")
    body = response.json()
    assert body["completed_today"] == 1
    assert body["completed_this_week"] == 1
    assert body["streak_days"] == 1
