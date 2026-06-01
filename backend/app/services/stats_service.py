"""
stats_service.py — Compute aggregate statistics from commitments.

All stats derive from the existing commitments table. No separate
storage. For our scale (single user, hundreds of commitments at most)
filtering in Python is plenty fast — no need for SQL aggregates yet.

"Completion time" is approximated by `updated_at` on done commitments.
Imperfect (a text edit to a done item shifts its apparent completion
time) but adequate for MVP.
"""

import logging
from datetime import UTC, date, datetime, timedelta

from app.models.commitment import CommitmentResponse, CommitmentStatus
from app.models.stats import DailyCompletion, StatsResponse
from app.services.commitment_service import CommitmentService

logger = logging.getLogger(__name__)


class StatsService:
    """
    Computes aggregate statistics from the user's commitments.

    Stateless — every call recomputes from current data. No caching
    (cheap enough to recompute on demand at our scale).
    """

    def __init__(self, commitment_service: CommitmentService) -> None:
        self._service = commitment_service

    def get_today_stats(self) -> StatsResponse:
        """
        Return today's stats: completion counts + 7-day sparkline + streak.
        """
        all_commitments = self._service.list()  # all statuses

        today = datetime.now(UTC).date()
        week_start = today - timedelta(days=6)  # 7 days inclusive

        # All done commitments, regardless of when
        done_commitments = [
            c for c in all_commitments if c.status == CommitmentStatus.DONE
        ]

        # Done commitments in the last 7 days (by updated_at date)
        done_this_week = [
            c for c in done_commitments
            if _to_date(c.updated_at) >= week_start
        ]

        completed_today = sum(
            1 for c in done_this_week if _to_date(c.updated_at) == today
        )
        completed_this_week = len(done_this_week)

        # 7-day series, oldest first (day index 0 = 6 days ago, index 6 = today)
        daily_completions: list[DailyCompletion] = []
        for offset in range(6, -1, -1):
            day = today - timedelta(days=offset)
            count = sum(
                1 for c in done_this_week if _to_date(c.updated_at) == day
            )
            daily_completions.append(
                DailyCompletion(date=day.isoformat(), count=count)
            )

        streak_days = self._compute_streak(done_commitments, today)

        return StatsResponse(
            completed_today=completed_today,
            completed_this_week=completed_this_week,
            streak_days=streak_days,
            daily_completions=daily_completions,
        )

    @staticmethod
    def _compute_streak(
        done_commitments: list[CommitmentResponse], today: date
    ) -> int:
        """
        Streak = consecutive days (going backwards) with at least one completion.

        Counts from today backwards if today has a completion. Otherwise
        counts from yesterday backwards if yesterday has one. Otherwise 0.

        This way the streak doesn't show 0 in the morning before you've
        done your first task of the day.
        """
        completion_dates: set[date] = {
            _to_date(c.updated_at) for c in done_commitments
        }

        if today in completion_dates:
            current = today
        elif (today - timedelta(days=1)) in completion_dates:
            current = today - timedelta(days=1)
        else:
            return 0

        streak = 0
        while current in completion_dates:
            streak += 1
            current -= timedelta(days=1)
        return streak


def _to_date(dt: datetime) -> date:
    """
    Convert a datetime (possibly naive, possibly tz-aware) to a date.

    All our datetimes should be UTC, but legacy SQLite rows may be naive.
    We just take the date portion either way.
    """
    return dt.date()
