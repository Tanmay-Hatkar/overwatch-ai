"""
test_goal_service.py — Unit tests for GoalService (ADR-0026).

The clock is pinned so the day of the week (which drives days_left and the
check-in state) is deterministic, and so week boundaries can be crossed on
purpose.
"""

import sqlite3
from datetime import UTC, date, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.models.goal import GoalCreate, GoalStatus, GoalUpdate
from app.models.user import UserResponse
from app.repositories.goal_repository import GoalRepository
from app.services.goal_service import GoalService

UTC_TZ = ZoneInfo("UTC")
TORONTO = ZoneInfo("America/Toronto")


class FakeClock:
    """Stand-in for `datetime` whose now() returns a settable instant."""

    current: datetime = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)  # a Wednesday

    @classmethod
    def now(cls, tz: ZoneInfo | None = None) -> datetime:
        return cls.current.astimezone(tz) if tz else cls.current


@pytest.fixture
def clock() -> type[FakeClock]:
    FakeClock.current = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)
    return FakeClock


@pytest.fixture
def goals(db_connection: sqlite3.Connection, clock: type[FakeClock]) -> GoalService:
    return GoalService(GoalRepository(db_connection), clock=clock)


def _apps(goals: GoalService, user: UserResponse, target: int = 10):
    return goals.create(user.id, GoalCreate(text="Job applications", target_count=target), UTC_TZ)


# ---------------------------------------------------------------------------
# create / list / week shape
# ---------------------------------------------------------------------------


def test_new_goal_starts_at_zero_mid_week(goals: GoalService, test_user: UserResponse) -> None:
    g = _apps(goals, test_user)
    assert g.done_this_week == 0
    assert g.remaining == 10
    assert g.week_start == date(2026, 10, 12)  # Monday
    assert g.days_left == 5  # Wed, Thu, Fri, Sat, Sun
    assert g.state == "in_progress"


def test_create_strips_whitespace(goals: GoalService, test_user: UserResponse) -> None:
    g = goals.create(test_user.id, GoalCreate(text="  Gym sessions  ", target_count=4), UTC_TZ)
    assert g.text == "Gym sessions"


def test_list_only_returns_active_goals(goals: GoalService, test_user: UserResponse) -> None:
    keep = _apps(goals, test_user)
    gone = goals.create(test_user.id, GoalCreate(text="Gym", target_count=3), UTC_TZ)
    goals.update(test_user.id, gone.id, GoalUpdate(status=GoalStatus.ARCHIVED), UTC_TZ)
    assert [g.id for g in goals.list(test_user.id, UTC_TZ)] == [keep.id]


def test_goals_are_scoped_to_their_owner(goals: GoalService, test_user: UserResponse) -> None:
    g = _apps(goals, test_user)
    stranger = uuid4()
    assert goals.get(stranger, g.id, UTC_TZ) is None
    assert goals.log(stranger, g.id, 1, UTC_TZ) is None
    assert goals.list(stranger, UTC_TZ) == []
    assert goals.delete(stranger, g.id) is False


# ---------------------------------------------------------------------------
# logging / undo
# ---------------------------------------------------------------------------


def test_log_adds_up(goals: GoalService, test_user: UserResponse) -> None:
    g = _apps(goals, test_user)
    goals.log(test_user.id, g.id, 2, UTC_TZ)
    after = goals.log(test_user.id, g.id, 1, UTC_TZ)
    assert after is not None
    assert after.done_this_week == 3
    assert after.remaining == 7


def test_reaching_target_is_met_and_remaining_never_negative(
    goals: GoalService, test_user: UserResponse
) -> None:
    g = _apps(goals, test_user, target=2)
    after = goals.log(test_user.id, g.id, 3, UTC_TZ)
    assert after is not None
    assert after.state == "met"
    assert after.remaining == 0
    assert after.done_this_week == 3


def test_undo_removes_most_recent_log_only(
    goals: GoalService, test_user: UserResponse, clock: type[FakeClock]
) -> None:
    g = _apps(goals, test_user)
    goals.log(test_user.id, g.id, 2, UTC_TZ)
    clock.current = clock.current.replace(hour=13)
    goals.log(test_user.id, g.id, 1, UTC_TZ)
    after = goals.undo_last_log(test_user.id, g.id, UTC_TZ)
    assert after is not None
    assert after.done_this_week == 2


def test_undo_with_nothing_this_week_is_a_noop(goals: GoalService, test_user: UserResponse) -> None:
    g = _apps(goals, test_user)
    after = goals.undo_last_log(test_user.id, g.id, UTC_TZ)
    assert after is not None
    assert after.done_this_week == 0


def test_undo_never_reaches_into_last_week(
    goals: GoalService, test_user: UserResponse, clock: type[FakeClock]
) -> None:
    g = _apps(goals, test_user)
    goals.log(test_user.id, g.id, 4, UTC_TZ)
    clock.current = datetime(2026, 10, 19, 9, 0, tzinfo=UTC)  # next Monday
    goals.undo_last_log(test_user.id, g.id, UTC_TZ)
    clock.current = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)  # back to last week
    after = goals.get(test_user.id, g.id, UTC_TZ)
    assert after is not None
    assert after.done_this_week == 4


# ---------------------------------------------------------------------------
# week boundaries + timezone
# ---------------------------------------------------------------------------


def test_new_week_starts_fresh(
    goals: GoalService, test_user: UserResponse, clock: type[FakeClock]
) -> None:
    g = _apps(goals, test_user)
    goals.log(test_user.id, g.id, 6, UTC_TZ)
    clock.current = datetime(2026, 10, 19, 0, 30, tzinfo=UTC)  # Monday 00:30
    fresh = goals.get(test_user.id, g.id, UTC_TZ)
    assert fresh is not None
    assert fresh.done_this_week == 0
    assert fresh.week_start == date(2026, 10, 19)
    assert fresh.days_left == 7


def test_week_boundary_follows_the_users_timezone(
    goals: GoalService, test_user: UserResponse, clock: type[FakeClock]
) -> None:
    """Sunday 9pm in Toronto is already Monday in UTC — it still counts as
    Toronto's current week."""
    g = goals.create(test_user.id, GoalCreate(text="Gym", target_count=4), TORONTO)
    clock.current = datetime(2026, 10, 19, 1, 0, tzinfo=UTC)  # Sun 21:00 Toronto
    after = goals.log(test_user.id, g.id, 1, TORONTO)
    assert after is not None
    assert after.week_start == date(2026, 10, 12)
    assert after.days_left == 1
    assert after.done_this_week == 1
    # In UTC that same log belongs to the new week.
    utc_view = goals.get(test_user.id, g.id, UTC_TZ)
    assert utc_view is not None
    assert utc_view.week_start == date(2026, 10, 19)
    assert utc_view.done_this_week == 1


# ---------------------------------------------------------------------------
# end-of-week check-in
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("day", "expected"),
    [(15, "in_progress"), (16, "check_in"), (17, "check_in"), (18, "check_in")],
)
def test_check_in_from_friday_when_not_met(
    goals: GoalService,
    test_user: UserResponse,
    clock: type[FakeClock],
    day: int,
    expected: str,
) -> None:
    g = _apps(goals, test_user)
    clock.current = datetime(2026, 10, day, 12, 0, tzinfo=UTC)
    current = goals.get(test_user.id, g.id, UTC_TZ)
    assert current is not None
    assert current.state == expected


def test_call_it_good_settles_this_week_only(
    goals: GoalService, test_user: UserResponse, clock: type[FakeClock]
) -> None:
    g = _apps(goals, test_user)
    clock.current = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)  # Friday
    settled = goals.decide_week(test_user.id, g.id, "call_it_good", UTC_TZ)
    assert settled is not None
    assert settled.state == "settled"
    clock.current = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)  # next Friday
    next_week = goals.get(test_user.id, g.id, UTC_TZ)
    assert next_week is not None
    assert next_week.state == "check_in"


def test_keep_going_stops_the_check_in_for_the_week(
    goals: GoalService, test_user: UserResponse, clock: type[FakeClock]
) -> None:
    g = _apps(goals, test_user)
    clock.current = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)  # Saturday
    kept = goals.decide_week(test_user.id, g.id, "keep_going", UTC_TZ)
    assert kept is not None
    assert kept.state == "in_progress"


def test_decision_can_be_taken_back(
    goals: GoalService, test_user: UserResponse, clock: type[FakeClock]
) -> None:
    g = _apps(goals, test_user)
    clock.current = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
    goals.decide_week(test_user.id, g.id, "call_it_good", UTC_TZ)
    undone = goals.decide_week(test_user.id, g.id, None, UTC_TZ)
    assert undone is not None
    assert undone.state == "check_in"


def test_lowering_target_can_meet_the_goal(
    goals: GoalService, test_user: UserResponse, clock: type[FakeClock]
) -> None:
    g = _apps(goals, test_user)
    goals.log(test_user.id, g.id, 7, UTC_TZ)
    clock.current = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
    lowered = goals.update(test_user.id, g.id, GoalUpdate(target_count=7), UTC_TZ)
    assert lowered is not None
    assert lowered.state == "met"


def test_delete_removes_goal(goals: GoalService, test_user: UserResponse) -> None:
    g = _apps(goals, test_user)
    goals.log(test_user.id, g.id, 1, UTC_TZ)
    assert goals.delete(test_user.id, g.id) is True
    assert goals.get(test_user.id, g.id, UTC_TZ) is None


def test_update_unknown_goal_returns_none(goals: GoalService, test_user: UserResponse) -> None:
    assert goals.update(test_user.id, uuid4(), GoalUpdate(text="x"), UTC_TZ) is None
    assert goals.decide_week(test_user.id, uuid4(), "keep_going", UTC_TZ) is None
    assert goals.undo_last_log(test_user.id, uuid4(), UTC_TZ) is None
