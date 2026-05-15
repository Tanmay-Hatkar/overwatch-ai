"""
test_commitment_service.py — Unit tests for CommitmentService.

For slice 1 the service is mostly delegation, so we test against a real
repository (via the `service` fixture in conftest.py). This still verifies:

  - Service correctly extracts fields from Pydantic input models.
  - Service returns what the repository returns.
  - The service's public API contract.

When future slices add real business logic to the service, we'll add tests
that use a mock repository to test service logic in isolation. For now,
real repo + in-memory DB is the simplest path.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.models.commitment import (
    CommitmentCreate,
    CommitmentStatus,
    CommitmentUpdate,
)
from app.services.commitment_service import CommitmentService


# ---------------------------------------------------------------------------
# create()
# ---------------------------------------------------------------------------


def test_create_extracts_text_and_due_at_from_payload(service: CommitmentService) -> None:
    """The service unpacks CommitmentCreate fields and forwards to the repository."""
    due = datetime.now(UTC) + timedelta(hours=1)
    payload = CommitmentCreate(text="Plan slice 2", due_at=due)

    result = service.create(payload)

    assert result.text == "Plan slice 2"
    assert result.due_at is not None
    assert result.due_at.isoformat() == due.isoformat()
    assert result.status == CommitmentStatus.OPEN


def test_create_works_without_due_date(service: CommitmentService) -> None:
    """due_at is optional in CommitmentCreate; service handles None."""
    payload = CommitmentCreate(text="No deadline", due_at=None)
    result = service.create(payload)

    assert result.text == "No deadline"
    assert result.due_at is None


# ---------------------------------------------------------------------------
# get()
# ---------------------------------------------------------------------------


def test_get_returns_existing(service: CommitmentService) -> None:
    """get() returns a commitment created through the service."""
    created = service.create(CommitmentCreate(text="Find me", due_at=None))
    fetched = service.get(created.id)

    assert fetched is not None
    assert fetched.id == created.id


def test_get_returns_none_for_missing(service: CommitmentService) -> None:
    """get() returns None for nonexistent ids."""
    assert service.get(uuid4()) is None


# ---------------------------------------------------------------------------
# list()
# ---------------------------------------------------------------------------


def test_list_returns_all_by_default(service: CommitmentService) -> None:
    """list() with no filter returns every commitment."""
    service.create(CommitmentCreate(text="A", due_at=None))
    service.create(CommitmentCreate(text="B", due_at=None))
    service.create(CommitmentCreate(text="C", due_at=None))

    assert len(service.list()) == 3


def test_list_filters_by_status(service: CommitmentService) -> None:
    """list(status=...) forwards the filter to the repository."""
    a = service.create(CommitmentCreate(text="A", due_at=None))
    service.create(CommitmentCreate(text="B", due_at=None))
    service.update(a.id, CommitmentUpdate(status=CommitmentStatus.DONE))

    assert len(service.list(status=CommitmentStatus.OPEN)) == 1
    assert len(service.list(status=CommitmentStatus.DONE)) == 1


# ---------------------------------------------------------------------------
# update()
# ---------------------------------------------------------------------------


def test_update_extracts_fields_from_payload(service: CommitmentService) -> None:
    """The service unpacks CommitmentUpdate fields and forwards to the repository."""
    created = service.create(CommitmentCreate(text="Original", due_at=None))
    payload = CommitmentUpdate(text="Changed", status=CommitmentStatus.DONE)

    updated = service.update(created.id, payload)

    assert updated is not None
    assert updated.text == "Changed"
    assert updated.status == CommitmentStatus.DONE


def test_update_returns_none_for_missing_id(service: CommitmentService) -> None:
    """update() returns None when the commitment doesn't exist."""
    assert service.update(uuid4(), CommitmentUpdate(text="X")) is None


# ---------------------------------------------------------------------------
# delete()
# ---------------------------------------------------------------------------


def test_delete_returns_true_on_success(service: CommitmentService) -> None:
    """delete() returns True when the commitment existed and was removed."""
    created = service.create(CommitmentCreate(text="To delete", due_at=None))
    assert service.delete(created.id) is True
    assert service.get(created.id) is None


def test_delete_returns_false_for_missing(service: CommitmentService) -> None:
    """delete() returns False when no commitment with that id exists."""
    assert service.delete(uuid4()) is False
