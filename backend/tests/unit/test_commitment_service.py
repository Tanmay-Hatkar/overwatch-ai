"""
test_commitment_service.py — Unit tests for CommitmentService.

The service is mostly delegation, tested against a real repository (via the
`service` fixture). Every method is scoped by user_id (slice 12), so a
module-level UID stands in for the signed-in user. commitments.user_id has
no FK constraint, so a bare UUID works without creating a user row.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.models.commitment import (
    CommitmentCreate,
    CommitmentStatus,
    CommitmentUpdate,
)
from app.services.commitment_service import CommitmentService

UID = uuid4()  # stands in for the signed-in user across these tests


# ---------------------------------------------------------------------------
# create()
# ---------------------------------------------------------------------------


def test_create_extracts_text_and_due_at_from_payload(service: CommitmentService) -> None:
    """The service unpacks CommitmentCreate fields and forwards to the repository."""
    due = datetime.now(UTC) + timedelta(hours=1)
    payload = CommitmentCreate(text="Plan slice 2", due_at=due)

    result = service.create(UID, payload)

    assert result.text == "Plan slice 2"
    assert result.due_at is not None
    assert result.due_at.isoformat() == due.isoformat()
    assert result.status == CommitmentStatus.OPEN


def test_create_works_without_due_date(service: CommitmentService) -> None:
    """due_at is optional in CommitmentCreate; service handles None."""
    payload = CommitmentCreate(text="No deadline", due_at=None)
    result = service.create(UID, payload)

    assert result.text == "No deadline"
    assert result.due_at is None


# ---------------------------------------------------------------------------
# get()
# ---------------------------------------------------------------------------


def test_get_returns_existing(service: CommitmentService) -> None:
    """get() returns a commitment created through the service."""
    created = service.create(UID, CommitmentCreate(text="Find me", due_at=None))
    fetched = service.get(UID, created.id)

    assert fetched is not None
    assert fetched.id == created.id


def test_get_returns_none_for_missing(service: CommitmentService) -> None:
    """get() returns None for nonexistent ids."""
    assert service.get(UID, uuid4()) is None


def test_get_is_scoped_to_owner(service: CommitmentService) -> None:
    """A different user can't see this user's commitment."""
    created = service.create(UID, CommitmentCreate(text="Private", due_at=None))
    other_user = uuid4()
    assert service.get(other_user, created.id) is None


# ---------------------------------------------------------------------------
# list()
# ---------------------------------------------------------------------------


def test_list_returns_all_by_default(service: CommitmentService) -> None:
    """list() with no filter returns every commitment for the user."""
    service.create(UID, CommitmentCreate(text="A", due_at=None))
    service.create(UID, CommitmentCreate(text="B", due_at=None))
    service.create(UID, CommitmentCreate(text="C", due_at=None))

    assert len(service.list(UID)) == 3


def test_list_is_scoped_to_owner(service: CommitmentService) -> None:
    """One user's commitments don't appear in another user's list."""
    service.create(UID, CommitmentCreate(text="Mine", due_at=None))
    assert len(service.list(uuid4())) == 0


def test_list_filters_by_status(service: CommitmentService) -> None:
    """list(status=...) forwards the filter to the repository."""
    a = service.create(UID, CommitmentCreate(text="A", due_at=None))
    service.create(UID, CommitmentCreate(text="B", due_at=None))
    service.update(UID, a.id, CommitmentUpdate(status=CommitmentStatus.DONE))

    assert len(service.list(UID, status=CommitmentStatus.OPEN)) == 1
    assert len(service.list(UID, status=CommitmentStatus.DONE)) == 1


# ---------------------------------------------------------------------------
# update()
# ---------------------------------------------------------------------------


def test_update_extracts_fields_from_payload(service: CommitmentService) -> None:
    """The service unpacks CommitmentUpdate fields and forwards to the repository."""
    created = service.create(UID, CommitmentCreate(text="Original", due_at=None))
    payload = CommitmentUpdate(text="Changed", status=CommitmentStatus.DONE)

    updated = service.update(UID, created.id, payload)

    assert updated is not None
    assert updated.text == "Changed"
    assert updated.status == CommitmentStatus.DONE


def test_update_returns_none_for_missing_id(service: CommitmentService) -> None:
    """update() returns None when the commitment doesn't exist."""
    assert service.update(UID, uuid4(), CommitmentUpdate(text="X")) is None


# ---------------------------------------------------------------------------
# delete()
# ---------------------------------------------------------------------------


def test_delete_returns_true_on_success(service: CommitmentService) -> None:
    """delete() returns True when the commitment existed and was removed."""
    created = service.create(UID, CommitmentCreate(text="To delete", due_at=None))
    assert service.delete(UID, created.id) is True
    assert service.get(UID, created.id) is None


def test_delete_returns_false_for_missing(service: CommitmentService) -> None:
    """delete() returns False when no commitment with that id exists."""
    assert service.delete(UID, uuid4()) is False
