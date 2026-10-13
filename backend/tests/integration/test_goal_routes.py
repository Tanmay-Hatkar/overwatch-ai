"""
test_goal_routes.py — Integration tests for the /goals endpoints (ADR-0026).

Full stack through TestClient -> route -> GoalService -> GoalRepository ->
in-memory DB. Week arithmetic is covered in test_goal_service.py with a
pinned clock; these tests check wiring, status codes, and auth.
"""

from uuid import uuid4

from fastapi.testclient import TestClient

TZ = "?timezone=America/Toronto"


def _create(client: TestClient, text: str = "Job applications", target: int = 10) -> dict:
    response = client.post(f"/goals{TZ}", json={"text": text, "target_count": target})
    assert response.status_code == 201
    return response.json()


def test_create_returns_goal_with_progress(authed_client: TestClient) -> None:
    body = _create(authed_client)
    assert body["text"] == "Job applications"
    assert body["target_count"] == 10
    assert body["done_this_week"] == 0
    assert body["remaining"] == 10
    assert body["status"] == "active"
    assert 1 <= body["days_left"] <= 7
    assert body["state"] in ("in_progress", "check_in")


def test_create_validates_target(authed_client: TestClient) -> None:
    assert authed_client.post("/goals", json={"text": "x", "target_count": 0}).status_code == 422
    assert authed_client.post("/goals", json={"text": "x", "target_count": 101}).status_code == 422
    assert authed_client.post("/goals", json={"text": "", "target_count": 3}).status_code == 422


def test_list_returns_created_goals(authed_client: TestClient) -> None:
    _create(authed_client, "Job applications")
    _create(authed_client, "Gym sessions", 4)
    body = authed_client.get(f"/goals{TZ}").json()
    assert [g["text"] for g in body] == ["Job applications", "Gym sessions"]


def test_log_and_undo(authed_client: TestClient) -> None:
    goal = _create(authed_client)
    logged = authed_client.post(f"/goals/{goal['id']}/log{TZ}", json={"amount": 3})
    assert logged.status_code == 200
    assert logged.json()["done_this_week"] == 3

    default = authed_client.post(f"/goals/{goal['id']}/log{TZ}", json={})
    assert default.json()["done_this_week"] == 4

    undone = authed_client.delete(f"/goals/{goal['id']}/log{TZ}")
    assert undone.status_code == 200
    assert undone.json()["done_this_week"] == 3


def test_log_rejects_bad_amount(authed_client: TestClient) -> None:
    goal = _create(authed_client)
    assert authed_client.post(f"/goals/{goal['id']}/log", json={"amount": 0}).status_code == 422


def test_patch_changes_target_and_archives(authed_client: TestClient) -> None:
    goal = _create(authed_client)
    patched = authed_client.patch(f"/goals/{goal['id']}{TZ}", json={"target_count": 6})
    assert patched.status_code == 200
    assert patched.json()["target_count"] == 6

    authed_client.patch(f"/goals/{goal['id']}", json={"status": "archived"})
    assert authed_client.get("/goals").json() == []


def test_week_decision_call_it_good(authed_client: TestClient) -> None:
    goal = _create(authed_client)
    response = authed_client.post(
        f"/goals/{goal['id']}/week-decision{TZ}", json={"decision": "call_it_good"}
    )
    assert response.status_code == 200
    assert response.json()["state"] == "settled"


def test_week_decision_rejects_unknown_value(authed_client: TestClient) -> None:
    goal = _create(authed_client)
    response = authed_client.post(f"/goals/{goal['id']}/week-decision", json={"decision": "quit"})
    assert response.status_code == 422


def test_delete(authed_client: TestClient) -> None:
    goal = _create(authed_client)
    assert authed_client.delete(f"/goals/{goal['id']}").status_code == 204
    assert authed_client.get("/goals").json() == []


def test_unknown_goal_is_404_everywhere(authed_client: TestClient) -> None:
    missing = uuid4()
    assert authed_client.patch(f"/goals/{missing}", json={"text": "x"}).status_code == 404
    assert authed_client.delete(f"/goals/{missing}").status_code == 404
    assert authed_client.post(f"/goals/{missing}/log", json={}).status_code == 404
    assert authed_client.delete(f"/goals/{missing}/log").status_code == 404
    assert (
        authed_client.post(f"/goals/{missing}/week-decision", json={"decision": None}).status_code
        == 404
    )


def test_requires_auth(client: TestClient) -> None:
    assert client.get("/goals").status_code == 401
    assert client.post("/goals", json={"text": "x", "target_count": 1}).status_code == 401
