"""
test_commitment_repository.py — Unit tests for CommitmentRepository.

Real in-memory SQLite (via the `repo` fixture). Every method is scoped by
user_id (slice 12); a module-level UID stands in for the owner. commitments
has no FK on user_id, so a bare UUID works without creating a user row.
"""

import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.models.commitment import CommitmentStatus
from app.repositories.commitment_repository import CommitmentRepository

UID = uuid4()  # the owner for these tests


# ---------------------------------------------------------------------------
# create()
# ---------------------------------------------------------------------------


def test_create_returns_commitment_with_open_status(repo: CommitmentRepository) -> None:
    """New commitments default to OPEN status and have matching create/update timestamps."""
    commitment = repo.create(UID, text="Write tests", due_at=None)

    assert commitment.text == "Write tests"
    assert commitment.status == CommitmentStatus.OPEN
    assert commitment.due_at is None
    assert commitment.created_at == commitment.updated_at


def test_create_with_due_date_persists_due_at(repo: CommitmentRepository) -> None:
    """A commitment with a due_at preserves the timestamp through the round-trip."""
    due = datetime.now(UTC) + timedelta(hours=2)
    commitment = repo.create(UID, text="Test due dates", due_at=due)

    assert commitment.due_at is not None
    assert commitment.due_at.isoformat() == due.isoformat()


def test_create_assigns_unique_ids(repo: CommitmentRepository) -> None:
    """Two commitments created back-to-back get different UUIDs."""
    a = repo.create(UID, text="A", due_at=None)
    b = repo.create(UID, text="B", due_at=None)
    assert a.id != b.id


# ---------------------------------------------------------------------------
# get()
# ---------------------------------------------------------------------------


def test_get_returns_existing_commitment(repo: CommitmentRepository) -> None:
    """get() returns the commitment that was created."""
    created = repo.create(UID, text="Find me", due_at=None)
    fetched = repo.get(UID, created.id)

    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.text == created.text


def test_get_returns_none_for_missing_id(repo: CommitmentRepository) -> None:
    """get() returns None when no commitment has that id."""
    assert repo.get(UID, uuid4()) is None


def test_get_is_scoped_to_owner(repo: CommitmentRepository) -> None:
    """A different user_id can't fetch this user's commitment."""
    created = repo.create(UID, text="Mine", due_at=None)
    assert repo.get(uuid4(), created.id) is None


# ---------------------------------------------------------------------------
# list()
# ---------------------------------------------------------------------------


def test_list_returns_all_commitments(repo: CommitmentRepository) -> None:
    """list() with no filter returns every commitment for the user."""
    repo.create(UID, text="First", due_at=None)
    repo.create(UID, text="Second", due_at=None)
    repo.create(UID, text="Third", due_at=None)

    assert len(repo.list(UID)) == 3


def test_list_is_scoped_to_owner(repo: CommitmentRepository) -> None:
    """Another user's list doesn't include this user's commitments."""
    repo.create(UID, text="Mine", due_at=None)
    assert repo.list(uuid4()) == []


def test_list_filters_by_status(repo: CommitmentRepository) -> None:
    """list(status=...) returns only commitments in that status."""
    a = repo.create(UID, text="A", due_at=None)
    repo.create(UID, text="B", due_at=None)
    repo.update(UID, a.id, status=CommitmentStatus.DONE)

    open_ones = repo.list(UID, status=CommitmentStatus.OPEN)
    done_ones = repo.list(UID, status=CommitmentStatus.DONE)

    assert len(open_ones) == 1
    assert open_ones[0].text == "B"
    assert len(done_ones) == 1
    assert done_ones[0].text == "A"


def test_list_returns_empty_when_no_matches(repo: CommitmentRepository) -> None:
    """list(status=...) returns an empty list when nothing matches."""
    repo.create(UID, text="A", due_at=None)
    assert repo.list(UID, status=CommitmentStatus.DONE) == []


def test_list_orders_by_created_at_descending(repo: CommitmentRepository) -> None:
    """Most recent commitments come first."""
    first = repo.create(UID, text="First", due_at=None)
    time.sleep(0.001)  # ensure distinct timestamps
    second = repo.create(UID, text="Second", due_at=None)

    result = repo.list(UID)
    assert result[0].id == second.id
    assert result[1].id == first.id


# ---------------------------------------------------------------------------
# update()
# ---------------------------------------------------------------------------


def test_update_changes_text(repo: CommitmentRepository) -> None:
    """update(text=...) changes only the text field."""
    c = repo.create(UID, text="Old", due_at=None)
    updated = repo.update(UID, c.id, text="New")

    assert updated is not None
    assert updated.text == "New"


def test_update_changes_status(repo: CommitmentRepository) -> None:
    """update(status=...) changes only the status field."""
    c = repo.create(UID, text="A", due_at=None)
    updated = repo.update(UID, c.id, status=CommitmentStatus.DONE)

    assert updated is not None
    assert updated.status == CommitmentStatus.DONE


def test_update_bumps_updated_at(repo: CommitmentRepository) -> None:
    """update() refreshes the updated_at timestamp."""
    c = repo.create(UID, text="A", due_at=None)
    time.sleep(0.001)
    updated = repo.update(UID, c.id, text="B")

    assert updated is not None
    assert updated.updated_at > c.updated_at


def test_update_preserves_unchanged_fields(repo: CommitmentRepository) -> None:
    """update() only changes provided fields; others stay the same."""
    c = repo.create(UID, text="Original", due_at=None)
    updated = repo.update(UID, c.id, status=CommitmentStatus.DONE)

    assert updated is not None
    assert updated.text == "Original"  # unchanged


def test_update_returns_none_for_missing_id(repo: CommitmentRepository) -> None:
    """update() returns None when the commitment doesn't exist."""
    assert repo.update(UID, uuid4(), text="X") is None


def test_update_with_no_changes_returns_existing(repo: CommitmentRepository) -> None:
    """update() with no fields specified returns the unchanged commitment."""
    c = repo.create(UID, text="A", due_at=None)
    result = repo.update(UID, c.id)  # no field kwargs

    assert result is not None
    assert result.id == c.id
    assert result.text == "A"


# ---------------------------------------------------------------------------
# delete()
# ---------------------------------------------------------------------------


def test_delete_removes_commitment(repo: CommitmentRepository) -> None:
    """delete() removes the commitment from storage."""
    c = repo.create(UID, text="To delete", due_at=None)

    assert repo.delete(UID, c.id) is True
    assert repo.get(UID, c.id) is None


def test_delete_returns_false_for_missing_id(repo: CommitmentRepository) -> None:
    """delete() returns False when the commitment doesn't exist."""
    assert repo.delete(UID, uuid4()) is False
