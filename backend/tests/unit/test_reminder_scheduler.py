"""
test_reminder_scheduler.py — Unit tests for ReminderScheduler._tick().

Tests the synchronous polling logic in isolation by directly invoking
_tick(). The async start/stop loop is integration territory; we focus
on the per-tick behavior:

  - First tick silently marks already-overdue items
  - Subsequent ticks fire pushes for newly-overdue items
  - Items already notified aren't re-pushed
  - No subscriptions → no broadcasts but still marked as notified

Uses a real in-memory SQLite via a context-managed connection patched
into the scheduler.
"""

import sqlite3
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.models.commitment import CommitmentCreate
from app.repositories.commitment_repository import CommitmentRepository
from app.repositories.push_subscription_repository import PushSubscriptionRepository
from app.services.commitment_service import CommitmentService
from app.services.reminder_scheduler import ReminderScheduler

CONN_TARGET = "app.services.reminder_scheduler.get_connection"


@pytest.fixture
def db_factory(tmp_path):
    """
    File-based SQLite so the scheduler can open/close fresh connections
    per tick (the way it does in production) while keeping the data.

    Returns a callable that:
      - opens + initializes the schema if the file doesn't have it yet
      - returns a fresh connection each call (for the patched get_connection)

    Plus a `setup_conn` accessor for the test to seed data without
    going through the patched factory.
    """
    db_path = tmp_path / "test.db"

    def _open() -> sqlite3.Connection:
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    # Initialize schema once
    init_conn = _open()
    init_conn.execute("""
        CREATE TABLE IF NOT EXISTS commitments (
            id TEXT PRIMARY KEY, text TEXT NOT NULL, due_at TEXT,
            status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        )
    """)
    init_conn.execute("""
        CREATE TABLE IF NOT EXISTS push_subscriptions (
            id TEXT PRIMARY KEY, endpoint TEXT NOT NULL UNIQUE,
            p256dh TEXT NOT NULL, auth TEXT NOT NULL, created_at TEXT NOT NULL
        )
    """)
    init_conn.commit()
    init_conn.close()

    return _open


@pytest.fixture
def scheduler():
    push = MagicMock()
    push.broadcast.return_value = []
    return ReminderScheduler(push_service=push, poll_interval_seconds=60)


def _seed_overdue_commitment(db_factory, text: str = "Old task") -> str:
    """Insert a commitment whose due_at is in the past. Returns its id."""
    conn = db_factory()
    try:
        repo = CommitmentRepository(conn)
        service = CommitmentService(repo)
        past = datetime.now(UTC) - timedelta(hours=1)
        return str(service.create(CommitmentCreate(text=text, due_at=past)).id)
    finally:
        conn.close()


def _seed_subscription(db_factory) -> None:
    conn = db_factory()
    try:
        PushSubscriptionRepository(conn).upsert(
            endpoint="https://push.example/a", p256dh="k", auth="a"
        )
    finally:
        conn.close()


def _seed_future_commitment(db_factory, text: str = "Future task") -> None:
    conn = db_factory()
    try:
        repo = CommitmentRepository(conn)
        service = CommitmentService(repo)
        future = datetime.now(UTC) + timedelta(hours=1)
        service.create(CommitmentCreate(text=text, due_at=future))
    finally:
        conn.close()


def test_first_tick_silently_marks_overdue(db_factory, scheduler) -> None:
    """The first tick after startup never sends pushes — even for overdue items."""
    _seed_overdue_commitment(db_factory)
    _seed_subscription(db_factory)

    with patch(CONN_TARGET, side_effect=db_factory):
        scheduler._tick()

    scheduler._push.broadcast.assert_not_called()
    assert len(scheduler._notified_ids) == 1


def test_second_tick_fires_push_for_newly_overdue(db_factory, scheduler) -> None:
    """After the first-tick suppression, new overdue items DO fire pushes."""
    # First tick: no commitments — flips _is_first_tick to False without pushing
    with patch(CONN_TARGET, side_effect=db_factory):
        scheduler._tick()
    assert scheduler._is_first_tick is False

    _seed_overdue_commitment(db_factory, "Newly due")
    _seed_subscription(db_factory)

    with patch(CONN_TARGET, side_effect=db_factory):
        scheduler._tick()

    scheduler._push.broadcast.assert_called_once()
    _subs, payload = scheduler._push.broadcast.call_args.args
    assert "Newly due" in payload.body


def test_no_subscriptions_still_marks_as_notified(db_factory, scheduler) -> None:
    """With no subscribers, we still record the id so future subscribers don't spam."""
    with patch(CONN_TARGET, side_effect=db_factory):
        scheduler._tick()  # exit first-tick state

    commitment_id = _seed_overdue_commitment(db_factory)

    with patch(CONN_TARGET, side_effect=db_factory):
        scheduler._tick()

    scheduler._push.broadcast.assert_not_called()
    assert commitment_id in scheduler._notified_ids


def test_already_notified_items_not_repushed(db_factory, scheduler) -> None:
    """An id in notified_ids is skipped on subsequent ticks."""
    with patch(CONN_TARGET, side_effect=db_factory):
        scheduler._tick()  # exit first-tick state

    commitment_id = _seed_overdue_commitment(db_factory)
    _seed_subscription(db_factory)
    scheduler._notified_ids.add(commitment_id)  # pre-mark as already notified

    with patch(CONN_TARGET, side_effect=db_factory):
        scheduler._tick()

    scheduler._push.broadcast.assert_not_called()


def test_future_commitments_not_pushed(db_factory, scheduler) -> None:
    """Commitments with due_at in the FUTURE are skipped."""
    with patch(CONN_TARGET, side_effect=db_factory):
        scheduler._tick()  # exit first-tick state

    _seed_future_commitment(db_factory, "Future thing")
    _seed_subscription(db_factory)

    with patch(CONN_TARGET, side_effect=db_factory):
        scheduler._tick()

    scheduler._push.broadcast.assert_not_called()
