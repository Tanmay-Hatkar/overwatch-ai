"""
test_stats_service.py — Unit tests for StatsService.

Most tests use the real CommitmentService (via the `service` fixture)
backed by in-memory SQLite. For tests that need to backdate `updated_at`,
we manipulate the DB directly.
"""

from datetime import UTC, date, datetime, timedelta

import pytest

from app.models.commitment import CommitmentCreate, CommitmentStatus, CommitmentUpdate
from app.services.commitment_service import CommitmentService
from app.services.stats_service import StatsService


@pytest.fixture
def stats_service(service: CommitmentService) -> StatsService:
    """StatsService wired to the in-memory CommitmentService fixture."""
    return StatsService(service)


def test_empty_state_returns_all_zeros(stats_service: StatsService) -> None:
    """No commitments → counts are 0, streak is 0, daily list has 7 zeros."""
    result = stats_service.get_today_stats()

    assert result.completed_today == 0
    assert result.completed_this_week == 0
    assert result.streak_days == 0
    assert len(result.daily_completions) == 7
    assert all(d.count == 0 for d in result.daily_completions)


def test_open_commitments_dont_count(
    stats_service: StatsService, service: CommitmentService
) -> None:
    """Open commitments (not yet done) shouldn't appear in any count."""
    service.create(CommitmentCreate(text="Not done", due_at=None))
    service.create(CommitmentCreate(text="Also not done", due_at=None))

    result = stats_service.get_today_stats()
    assert result.completed_today == 0
    assert result.completed_this_week == 0


def test_one_done_today(
    stats_service: StatsService, service: CommitmentService
) -> None:
    """A commitment marked done today increments today + this_week + streak."""
    c = service.create(CommitmentCreate(text="Did it", due_at=None))
    service.update(c.id, CommitmentUpdate(status=CommitmentStatus.DONE))

    result = stats_service.get_today_stats()
    assert result.completed_today == 1
    assert result.completed_this_week == 1
    assert result.streak_days == 1


def test_daily_completions_has_seven_entries_in_chronological_order(
    stats_service: StatsService,
) -> None:
    """The 7-day list always has length 7, oldest first."""
    result = stats_service.get_today_stats()
    assert len(result.daily_completions) == 7

    # Verify chronological order: each date is one day after the previous
    dates = [date.fromisoformat(d.date) for d in result.daily_completions]
    for i in range(1, 7):
        assert (dates[i] - dates[i - 1]).days == 1

    # Last entry is today
    today = datetime.now(UTC).date()
    assert dates[-1] == today


def test_backdated_completion_counts_against_correct_day(
    stats_service: StatsService, service: CommitmentService, db_connection
) -> None:
    """A commitment done 3 days ago should appear in this_week but not today."""
    c = service.create(CommitmentCreate(text="Old win", due_at=None))
    service.update(c.id, CommitmentUpdate(status=CommitmentStatus.DONE))

    # Backdate updated_at directly in the DB to 3 days ago
    three_days_ago = (datetime.now(UTC) - timedelta(days=3)).isoformat()
    db_connection.execute(
        "UPDATE commitments SET updated_at = ? WHERE id = ?",
        (three_days_ago, str(c.id)),
    )
    db_connection.commit()

    result = stats_service.get_today_stats()
    assert result.completed_today == 0
    assert result.completed_this_week == 1


def test_streak_resets_on_gap(
    stats_service: StatsService, service: CommitmentService, db_connection
) -> None:
    """Completions on day -3 and today (with -1, -2 empty) → streak is 1."""
    # Done today (will count for streak)
    c1 = service.create(CommitmentCreate(text="Today", due_at=None))
    service.update(c1.id, CommitmentUpdate(status=CommitmentStatus.DONE))

    # Done 3 days ago (gap in between)
    c2 = service.create(CommitmentCreate(text="Old", due_at=None))
    service.update(c2.id, CommitmentUpdate(status=CommitmentStatus.DONE))
    three_days_ago = (datetime.now(UTC) - timedelta(days=3)).isoformat()
    db_connection.execute(
        "UPDATE commitments SET updated_at = ? WHERE id = ?",
        (three_days_ago, str(c2.id)),
    )
    db_connection.commit()

    result = stats_service.get_today_stats()
    # Today counts, but -1 and -2 are empty so streak doesn't extend back
    assert result.streak_days == 1


def test_streak_starts_from_yesterday_if_today_has_no_completions(
    stats_service: StatsService, service: CommitmentService, db_connection
) -> None:
    """If today has no completions but yesterday does, streak still counts."""
    c = service.create(CommitmentCreate(text="Yesterday's win", due_at=None))
    service.update(c.id, CommitmentUpdate(status=CommitmentStatus.DONE))
    yesterday = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    db_connection.execute(
        "UPDATE commitments SET updated_at = ? WHERE id = ?",
        (yesterday, str(c.id)),
    )
    db_connection.commit()

    result = stats_service.get_today_stats()
    assert result.completed_today == 0
    assert result.streak_days == 1  # extends back from yesterday
