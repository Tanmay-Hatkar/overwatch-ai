"""
test_stale_check_scheduler.py — Unit tests for StaleCheckScheduler._tick().

Dedup is persisted in the database (commitments.stale_check_sent_at),
not in-memory — so "exactly once, ever" is verified by re-running _tick()
across multiple ticks and asserting no second ask happens once
stale_check_sent_at is set.
"""

import sqlite3
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from app.migrations import run_migrations
from app.models.commitment import CommitmentCreate
from app.repositories.commitment_repository import CommitmentRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.user_repository import UserRepository
from app.services.commitment_service import CommitmentService
from app.services.stale_check_scheduler import StaleCheckScheduler

CONN_TARGET = "app.services.stale_check_scheduler.get_connection"
THRESHOLD_HOURS = 4


@pytest.fixture
def db_factory(tmp_path):
    """
    File-based SQLite so the scheduler can open/close fresh connections per
    tick (as in production). Runs the real migrations and seeds one user.

    Returns a callable returning a fresh connection each call.
    """
    db_path = tmp_path / "test.db"

    def _open() -> sqlite3.Connection:
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    init_conn = _open()
    run_migrations(init_conn)
    UserRepository(init_conn).create(
        google_id="g-stale", email="stale@example.com", name="Stale", picture=None
    )
    init_conn.close()

    return _open


def _uid(db_factory):
    """The id of the single seeded user."""
    conn = db_factory()
    try:
        return UserRepository(conn).list_all_ids()[0]
    finally:
        conn.close()


@pytest.fixture
def scheduler():
    return StaleCheckScheduler(poll_interval_seconds=60, threshold_hours=THRESHOLD_HOURS)


def _seed_dormant_commitment(db_factory, text: str = "Dormant plan", due_at=None) -> str:
    """Create a commitment, then backdate updated_at so it reads as dormant."""
    conn = db_factory()
    try:
        service = CommitmentService(CommitmentRepository(conn))
        commitment = service.create(_uid(db_factory), CommitmentCreate(text=text, due_at=due_at))
        stale_updated_at = (datetime.now(UTC) - timedelta(hours=THRESHOLD_HOURS + 1)).isoformat()
        conn.execute(
            "UPDATE commitments SET updated_at = ? WHERE id = ?",
            (stale_updated_at, str(commitment.id)),
        )
        conn.commit()
        return str(commitment.id)
    finally:
        conn.close()


def _seed_fresh_commitment(db_factory, text: str = "Fresh plan") -> None:
    conn = db_factory()
    try:
        service = CommitmentService(CommitmentRepository(conn))
        service.create(_uid(db_factory), CommitmentCreate(text=text, due_at=None))
    finally:
        conn.close()


def _conversation_turns(db_factory) -> list:
    conn = db_factory()
    try:
        return ConversationRepository(conn).recent(_uid(db_factory), limit=50)
    finally:
        conn.close()


def _stale_check_sent_at(db_factory, commitment_id: str):
    conn = db_factory()
    try:
        row = conn.execute(
            "SELECT stale_check_sent_at FROM commitments WHERE id = ?", (commitment_id,)
        ).fetchone()
        return row["stale_check_sent_at"]
    finally:
        conn.close()


def test_first_tick_silently_marks_dormant_without_asking(db_factory, scheduler) -> None:
    """The first tick after startup never logs a check-in turn — even for
    already-dormant items — but it DOES mark them sent."""
    commitment_id = _seed_dormant_commitment(db_factory)

    with patch(CONN_TARGET, side_effect=db_factory):
        scheduler._tick()

    assert _conversation_turns(db_factory) == []
    assert _stale_check_sent_at(db_factory, commitment_id) is not None


def test_second_tick_asks_about_newly_dormant_item(db_factory, scheduler) -> None:
    """After first-tick suppression, a newly-dormant item DOES get asked
    about via a logged assistant conversation turn, and is marked sent."""
    with patch(CONN_TARGET, side_effect=db_factory):
        scheduler._tick()  # exit first-tick state (nothing dormant yet)

    commitment_id = _seed_dormant_commitment(db_factory, "Newly dormant")

    with patch(CONN_TARGET, side_effect=db_factory):
        scheduler._tick()

    turns = _conversation_turns(db_factory)
    assert len(turns) == 1
    assert turns[0].role == "assistant"
    assert "Newly dormant" in turns[0].content
    assert _stale_check_sent_at(db_factory, commitment_id) is not None


def test_asked_only_once_across_multiple_ticks(db_factory, scheduler) -> None:
    """Once stale_check_sent_at is set, later ticks never ask again — the
    'fires once per commitment, ever' guarantee (PRD: respectful by default)."""
    with patch(CONN_TARGET, side_effect=db_factory):
        scheduler._tick()  # exit first-tick state

    _seed_dormant_commitment(db_factory)

    with patch(CONN_TARGET, side_effect=db_factory):
        scheduler._tick()
    assert len(_conversation_turns(db_factory)) == 1

    with patch(CONN_TARGET, side_effect=db_factory):
        scheduler._tick()  # third tick — same commitment, still dormant

    assert len(_conversation_turns(db_factory)) == 1  # still just the one ask


def test_marks_sent_even_when_logging_the_turn_fails(db_factory, scheduler) -> None:
    """The guarantee is "we asked once," not "they saw it": a failure to log
    the conversation turn still records stale_check_sent_at, so a broken
    write can't turn into a repeated check-in later."""
    with patch(CONN_TARGET, side_effect=db_factory):
        scheduler._tick()  # exit first-tick state

    commitment_id = _seed_dormant_commitment(db_factory)

    with (
        patch(CONN_TARGET, side_effect=db_factory),
        patch.object(ConversationRepository, "append", side_effect=sqlite3.OperationalError),
    ):
        scheduler._tick()

    assert _conversation_turns(db_factory) == []
    assert _stale_check_sent_at(db_factory, commitment_id) is not None


def test_fresh_commitments_not_flagged(db_factory, scheduler) -> None:
    """A recently-touched open commitment isn't dormant yet — not asked about."""
    with patch(CONN_TARGET, side_effect=db_factory):
        scheduler._tick()  # exit first-tick state

    _seed_fresh_commitment(db_factory)

    with patch(CONN_TARGET, side_effect=db_factory):
        scheduler._tick()

    assert _conversation_turns(db_factory) == []
