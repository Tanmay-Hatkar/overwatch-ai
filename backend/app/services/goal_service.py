"""
goal_service.py — Business logic for weekly rate goals (ADR-0026).

Cadence (PRD §11's open question, answered here): a goal's week is the
user's local calendar week, Monday 00:00 to the next Monday 00:00. Not a
sliding 7 days — "this week" in conversation means the calendar week, and
a fixed reset is what lets a bad week end cleanly instead of trailing
into the next one.

Progress is computed on read from goal_logs in that window, so it is
always consistent with undo, timezone, and the week boundary.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from app.config import settings
from app.models.goal import (
    GoalCreate,
    GoalRecord,
    GoalResponse,
    GoalUpdate,
    GoalWeekState,
    WeekDecision,
)
from app.repositories.goal_repository import GoalRepository

logger = logging.getLogger(__name__)


class GoalService:
    """Weekly rate goals: CRUD, progress logging, and this-week status."""

    def __init__(self, repo: GoalRepository, clock: type[datetime] = datetime) -> None:
        """
        Args:
            repo: Goal data access.
            clock: Source of "now" (anything with a tz-aware `.now(tz)`);
                injectable so tests can pin the day of the week.
        """
        self._repo = repo
        self._clock = clock

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create(self, user_id: UUID, payload: GoalCreate, user_tz: ZoneInfo) -> GoalResponse:
        """Create a goal and return it with (empty) progress for this week."""
        logger.info("Creating goal for user %s: %r x%d", user_id, payload.text[:50], payload.target_count)
        record = self._repo.create(user_id, payload.text.strip(), payload.target_count)
        return self._with_progress(user_id, record, user_tz)

    def list(self, user_id: UUID, user_tz: ZoneInfo) -> list[GoalResponse]:
        """Every active goal with this week's progress."""
        return [self._with_progress(user_id, r, user_tz) for r in self._repo.list(user_id)]

    def get(self, user_id: UUID, goal_id: UUID, user_tz: ZoneInfo) -> GoalResponse | None:
        """One goal with progress, or None if it isn't this user's."""
        record = self._repo.get(user_id, goal_id)
        return self._with_progress(user_id, record, user_tz) if record else None

    def update(
        self, user_id: UUID, goal_id: UUID, payload: GoalUpdate, user_tz: ZoneInfo
    ) -> GoalResponse | None:
        """Partially update a goal. Returns None if it isn't this user's."""
        record = self._repo.update(
            user_id,
            goal_id,
            text=payload.text.strip() if payload.text else None,
            target_count=payload.target_count,
            status=payload.status,
        )
        return self._with_progress(user_id, record, user_tz) if record else None

    def delete(self, user_id: UUID, goal_id: UUID) -> bool:
        """Hard-delete a goal and its logs."""
        logger.info("Deleting goal %s (user %s)", goal_id, user_id)
        return self._repo.delete(user_id, goal_id)

    # ------------------------------------------------------------------
    # Progress
    # ------------------------------------------------------------------

    def log(
        self, user_id: UUID, goal_id: UUID, amount: int, user_tz: ZoneInfo
    ) -> GoalResponse | None:
        """Add `amount` of progress now. Returns None if the goal isn't this user's."""
        if self._repo.get(user_id, goal_id) is None:
            return None
        self._repo.add_log(user_id, goal_id, amount, self._clock.now(UTC))
        return self.get(user_id, goal_id, user_tz)

    def undo_last_log(
        self, user_id: UUID, goal_id: UUID, user_tz: ZoneInfo
    ) -> GoalResponse | None:
        """
        Remove this week's most recent log. Earlier weeks are never touched.

        Returns:
            The goal after the undo (unchanged if there was nothing to undo
            this week), or None if the goal isn't this user's.
        """
        if self._repo.get(user_id, goal_id) is None:
            return None
        since, until = self._week_window_utc(self._week_start(user_tz), user_tz)
        self._repo.delete_latest_log(user_id, goal_id, since, until)
        return self.get(user_id, goal_id, user_tz)

    def decide_week(
        self, user_id: UUID, goal_id: UUID, decision: WeekDecision | None, user_tz: ZoneInfo
    ) -> GoalResponse | None:
        """
        Record the answer to this week's check-in.

        'call_it_good' closes the week by the user's choice — agency, not
        failure. 'keep_going' just means "don't ask again this week". None
        takes the answer back. Next Monday starts fresh either way.
        """
        record = self._repo.set_week_decision(user_id, goal_id, decision, self._week_start(user_tz))
        return self._with_progress(user_id, record, user_tz) if record else None

    # ------------------------------------------------------------------
    # Week arithmetic
    # ------------------------------------------------------------------

    def _week_start(self, user_tz: ZoneInfo) -> date:
        """Monday of the user's current local week."""
        today = self._clock.now(user_tz).date()
        return today - timedelta(days=today.weekday())

    @staticmethod
    def _week_window_utc(week_start: date, user_tz: ZoneInfo) -> tuple[datetime, datetime]:
        """[Monday 00:00, next Monday 00:00) in user_tz, as UTC instants."""
        start = datetime.combine(week_start, time.min, tzinfo=user_tz)
        end = datetime.combine(week_start + timedelta(days=7), time.min, tzinfo=user_tz)
        return start.astimezone(UTC), end.astimezone(UTC)

    def _with_progress(self, user_id: UUID, record: GoalRecord, user_tz: ZoneInfo) -> GoalResponse:
        """Attach this week's done/remaining/days-left/state to a stored goal."""
        week_start = self._week_start(user_tz)
        since, until = self._week_window_utc(week_start, user_tz)
        done = self._repo.sum_logs(user_id, record.id, since, until)
        days_left = 7 - self._clock.now(user_tz).date().weekday()
        return GoalResponse(
            id=record.id,
            text=record.text,
            target_count=record.target_count,
            status=record.status,
            created_at=record.created_at,
            updated_at=record.updated_at,
            week_start=week_start,
            done_this_week=done,
            remaining=max(0, record.target_count - done),
            days_left=days_left,
            state=self._state(record, done, days_left, week_start),
        )

    @staticmethod
    def _state(record: GoalRecord, done: int, days_left: int, week_start: date) -> GoalWeekState:
        """Classify where the goal stands this week (see GoalWeekState)."""
        if done >= record.target_count:
            return "met"
        decided = record.decision if record.decision_week == week_start else None
        if decided == "call_it_good":
            return "settled"
        if decided is None and days_left <= settings.goal_check_in_days_left:
            return "check_in"
        return "in_progress"

