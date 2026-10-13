"""
stale_check_scheduler.py — Background task that asks about dormant plans.

How it works:
  - Started in FastAPI's lifespan on app startup
  - Polls every STALE_CHECK_POLL_INTERVAL_SECONDS
  - For each user, for each OPEN commitment that has gone quiet (no update
    in STALE_CHECK_THRESHOLD_HOURS) and hasn't been asked about before, we
    ask ONCE — ever — "still the plan?" as a logged assistant conversation
    turn. The mobile app schedules its own on-device notification for the
    same moment (mobile/src/lib/notifications.js) and shows this turn, with
    its reply chips, when the user opens the chat.
  - Dedup is persisted in the database (commitments.stale_check_sent_at),
    NOT in-memory — a process restart does not reset the "have we asked"
    state, honoring the "fires once per
    commitment, ever" guarantee (see docs/adr/0017-stale-plan-detection.md).

First-tick handling: the very first tick after a fresh deploy of this
feature could find many pre-existing dormant commitments simultaneously
(anything that predates the migration and happens to already be quiet).
Firing a check-in burst for all of them at once would be jarring, so the
first tick of each process silently marks any
current candidates as sent without asking, and only ticks after that
actually ask.

"Respectful by default, aggressive only on permission" (PRD): this
scheduler never repeats a check-in. Once stale_check_sent_at is set for a
commitment, it is never a candidate again.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.config import settings
from app.database import get_connection
from app.models.commitment import CommitmentResponse
from app.repositories.commitment_repository import CommitmentRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.user_repository import UserRepository
from app.services.commitment_service import CommitmentService

logger = logging.getLogger(__name__)


class StaleCheckScheduler:
    """
    Background polling task that asks about dormant open commitments,
    once each, ever. One instance per app process.
    """

    def __init__(
        self,
        poll_interval_seconds: int | None = None,
        threshold_hours: int | None = None,
    ) -> None:
        self._interval = poll_interval_seconds or settings.stale_check_poll_interval_seconds
        self._threshold_hours = threshold_hours or settings.stale_check_threshold_hours
        self._is_first_tick = True
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    def start(self) -> None:
        """Spawn the background polling task. Idempotent."""
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="stale-check-scheduler")
        logger.info(f"StaleCheckScheduler started (interval={self._interval}s)")

    async def stop(self) -> None:
        """Signal the task to stop and wait for it to finish."""
        self._stop_event.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("StaleCheckScheduler did not stop within 5s; cancelling")
                self._task.cancel()
        logger.info("StaleCheckScheduler stopped")

    # ------------------------------------------------------------------

    async def _run(self) -> None:
        """Main polling loop."""
        while not self._stop_event.is_set():
            try:
                await asyncio.get_running_loop().run_in_executor(None, self._tick)
            except Exception as e:
                logger.warning(f"StaleCheckScheduler tick failed: {e}")

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._interval)
            except asyncio.TimeoutError:
                # Expected — normal interval elapsed without a stop signal
                pass

    def _tick(self) -> None:
        """
        One polling cycle. Runs in a worker thread (sync code, blocking calls).

        Iterates every user, scoping commitments and conversation history to
        that user, so each person is only ever asked about their
        own dormant plans.
        """
        conn = get_connection()
        try:
            commitment_service = CommitmentService(CommitmentRepository(conn))
            conversation_repo = ConversationRepository(conn)
            user_repo = UserRepository(conn)

            now = datetime.now(UTC)
            updated_before = now - timedelta(hours=self._threshold_hours)
            today = now.date()
            first_tick = self._is_first_tick

            for user_id in user_repo.list_all_ids():
                candidates = commitment_service.list_stale_candidates(
                    user_id, updated_before, today
                )
                if not candidates:
                    continue

                if first_tick:
                    self._silently_mark_sent(commitment_service, user_id, candidates)
                    continue

                for commitment in candidates:
                    self._ask_about_one(
                        commitment_service, conversation_repo, user_id, commitment
                    )

            self._is_first_tick = False
        finally:
            conn.close()

    def _silently_mark_sent(
        self,
        commitment_service: CommitmentService,
        user_id: UUID,
        candidates: list[CommitmentResponse],
    ) -> None:
        """First-tick suppression: record 'asked' without actually asking."""
        for c in candidates:
            commitment_service.mark_stale_check_sent(user_id, c.id)
        logger.info(
            "StaleCheckScheduler first tick: silently marked %d pre-existing "
            "dormant items for user %s",
            len(candidates), user_id,
        )

    def _ask_about_one(
        self,
        commitment_service: CommitmentService,
        conversation_repo: ConversationRepository,
        user_id: UUID,
        commitment: CommitmentResponse,
    ) -> None:
        """
        Ask about one dormant commitment via a logged conversation turn,
        then mark it sent even if logging failed — the guarantee is
        "we asked once," not "they saw it."
        """
        body = f'Still the plan — "{commitment.text}"? Or has today changed?'

        try:
            conversation_repo.append(user_id, "assistant", body)
        except Exception as e:
            logger.warning(f"StaleCheckScheduler: failed to log conversation turn: {e}")

        commitment_service.mark_stale_check_sent(user_id, commitment.id)
        logger.info(
            "StaleCheckScheduler: asked about '%s' (user %s)",
            commitment.text[:40], user_id,
        )
