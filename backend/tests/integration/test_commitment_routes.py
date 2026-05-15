"""
test_commitment_routes.py — Integration tests for the /commitments endpoints.

Strategy: use FastAPI's TestClient (via the `client` fixture in conftest.py)
to send real HTTP requests through the full stack:

    TestClient -> FastAPI -> route handler -> service -> repository -> in-memory DB

Each test exercises one endpoint end-to-end. We verify:
  - HTTP status codes (201 for create, 200 for read, 204 for delete, 404 for missing).
  - Response body shape and contents.
  - Side effects (e.g., delete actually removes the record).

These are "integration" tests because they cross layer boundaries. They run
slightly slower than pure unit tests but catch wiring bugs (e.g., a wrong
import in main.py) that unit tests would miss.
"""

from uuid import uuid4

from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# POST /commitments
# ---------------------------------------------------------------------------


def test_post_creates_commitment(client: TestClient) -> None:
    """POST returns 201 with the created commitment including server-generated fields."""
    response = client.post("/commitments", json={"text": "Test create", "due_at": None})

    assert response.status_code == 201
    body = response.json()
    assert body["text"] == "Test create"
    assert body["status"] == "open"
    assert body["due_at"] is None
    assert "id" in body
    assert "created_at" in body
    assert "updated_at" in body


def test_post_rejects_empty_text(client: TestClient) -> None:
    """Pydantic validation rejects empty text (min_length=1)."""
    response = client.post("/commitments", json={"text": "", "due_at": None})
    assert response.status_code == 422  # Unprocessable Entity


def test_post_rejects_missing_text(client: TestClient) -> None:
    """text is required."""
    response = client.post("/commitments", json={"due_at": None})
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /commitments (list)
# ---------------------------------------------------------------------------


def test_get_list_returns_empty_array_when_no_commitments(client: TestClient) -> None:
    """An empty database returns an empty array, not 404."""
    response = client.get("/commitments")
    assert response.status_code == 200
    assert response.json() == []


def test_get_list_returns_all_commitments(client: TestClient) -> None:
    """List returns every commitment that's been created."""
    client.post("/commitments", json={"text": "A", "due_at": None})
    client.post("/commitments", json={"text": "B", "due_at": None})

    response = client.get("/commitments")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2


def test_get_list_filters_by_status(client: TestClient) -> None:
    """?status_filter=done returns only done commitments."""
    a = client.post("/commitments", json={"text": "A", "due_at": None}).json()
    client.post("/commitments", json={"text": "B", "due_at": None})
    client.patch(f"/commitments/{a['id']}", json={"status": "done"})

    response = client.get("/commitments", params={"status_filter": "done"})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["text"] == "A"


# ---------------------------------------------------------------------------
# GET /commitments/{id}
# ---------------------------------------------------------------------------


def test_get_by_id_returns_commitment(client: TestClient) -> None:
    """GET by id returns the matching commitment."""
    created = client.post("/commitments", json={"text": "Find me", "due_at": None}).json()

    response = client.get(f"/commitments/{created['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_get_by_id_returns_404_for_missing(client: TestClient) -> None:
    """GET an id that doesn't exist returns 404."""
    response = client.get(f"/commitments/{uuid4()}")
    assert response.status_code == 404


def test_get_by_id_returns_422_for_invalid_uuid(client: TestClient) -> None:
    """A non-UUID path param returns 422 (validation error)."""
    response = client.get("/commitments/not-a-uuid")
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /commitments/{id}
# ---------------------------------------------------------------------------


def test_patch_updates_status(client: TestClient) -> None:
    """PATCH with a new status returns 200 and the updated commitment."""
    created = client.post("/commitments", json={"text": "A", "due_at": None}).json()

    response = client.patch(f"/commitments/{created['id']}", json={"status": "done"})

    assert response.status_code == 200
    assert response.json()["status"] == "done"


def test_patch_updates_text(client: TestClient) -> None:
    """PATCH can change just the text field."""
    created = client.post("/commitments", json={"text": "Old", "due_at": None}).json()

    response = client.patch(f"/commitments/{created['id']}", json={"text": "New"})

    assert response.status_code == 200
    assert response.json()["text"] == "New"


def test_patch_returns_404_for_missing(client: TestClient) -> None:
    """PATCH on a missing id returns 404."""
    response = client.patch(f"/commitments/{uuid4()}", json={"text": "X"})
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /commitments/{id}
# ---------------------------------------------------------------------------


def test_delete_removes_commitment(client: TestClient) -> None:
    """DELETE returns 204 and the commitment is gone from subsequent reads."""
    created = client.post("/commitments", json={"text": "Delete me", "due_at": None}).json()

    delete_response = client.delete(f"/commitments/{created['id']}")
    assert delete_response.status_code == 204

    # Confirm it's actually gone
    get_response = client.get(f"/commitments/{created['id']}")
    assert get_response.status_code == 404


def test_delete_returns_404_for_missing(client: TestClient) -> None:
    """DELETE on a missing id returns 404."""
    response = client.delete(f"/commitments/{uuid4()}")
    assert response.status_code == 404
