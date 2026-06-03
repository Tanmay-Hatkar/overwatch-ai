"""
reminder_scheduler.py — Background task that fires push notifications
for newly-overdue commitments.

How it works:
  - Started in FastAPI's lifespan on app startup
  - Polls every REMINDER_POLL_INTERVAL_SECONDS
  - For each open commitment whose due_at has passed AND that we haven't
    notified about yet this process lifetime, broadcasts a push to all
    subscriptions
  - Tracks notified commitment IDs in memory (in-process). Restart clears
    this — currently-overdue items will be silently marked on the first
    tick after restart (no notification burst).

In-memory tracking is intentional for MVP. A persistent "last notified"
column on commitments would be more correct (survive restart, dedupe
across multiple app instances) but adds a migration. Defer that work.
"""

import asyncio
import logging
from datetime import UTC, datetime

from app.config import settings
from app.database import get_connection
from app.models.commitment import CommitmentStatus
from app.repositories.commitment_repository import CommitmentRepository
from app.repositories.push_subscription_repository import PushSubscriptionRepository
from app.services.commitment_service import CommitmentService
from app.services.push_service import PushPayload, PushService

logger = logging.getLogger(__name__)


class ReminderScheduler:
    """
    Background polling task that fires push notifications for newly-overdue
    commitments. One instance per app process.
    """

    def __init__(self, push_service: PushService, poll_interval_seconds: int | None = None):
        self._push = push_service
        self._interval = poll_interval_seconds or settings.reminder_poll_interval_seconds
        self._notified_ids: set[str] = set()
        self._is_first_tick = True
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    def start(self) -> None:
        """Spawn the background polling task. Idempotent."""
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="reminder-scheduler")
        logger.info(f"ReminderScheduler started (interval={self._interval}s)")

    async def stop(self) -> None:
        """Signal the task to stop and wait for it to finish."""
        self._stop_event.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("ReminderScheduler did not stop within 5s; cancelling")
                self._task.cancel()
        logger.info("ReminderScheduler stopped")

    # ------------------------------------------------------------------

    async def _run(self) -> None:
        """Main polling loop."""
        while not self._stop_event.is_set():
            try:
                await asyncio.get_running_loop().run_in_executor(None, self._tick)
            except Exception as e:
                logger.warning(f"ReminderScheduler tick failed: {e}")

            # Sleep until next tick OR until stop is signaled, whichever first.
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._interval)
            except asyncio.TimeoutError:
                # Expected — normal interval elapsed without a stop signal
                pass

    def _tick(self) -> None:
        """One polling cycle. Runs in a worker thread (sync code, blocking calls)."""
        conn = get_connection()
        try:
            commitment_repo = CommitmentRepository(conn)
            commitment_service = CommitmentService(commitment_repo)
            sub_repo = PushSubscriptionRepository(conn)

            now = datetime.now(UTC)
            open_commitments = commitment_service.list(status=CommitmentStatus.OPEN)

            newly_overdue = []
            for c in open_commitments:
                if c.due_at is None:
                    continue
                if str(c.id) in self._notified_ids:
                    continue
                due = c.due_at if c.due_at.tzinfo else c.due_at.replace(tzinfo=UTC)
                if due > now:
                    continue
                newly_overdue.append(c)

            if not newly_overdue:
                self._is_first_tick = False
                return

            if self._is_first_tick:
                # First tick after startup — suppress already-overdue items.
                for c in newly_overdue:
                    self._notified_ids.add(str(c.id))
                logger.info(
                    f"ReminderScheduler first tick: silently marked "
                    f"{len(newly_overdue)} already-overdue items as notified"
                )
                self._is_first_tick = False
                return

            subscriptions = sub_repo.list_all()
            if not subscriptions:
                # No subscribers — still mark as notified so we don't spam
                # when someone subscribes later.
                for c in newly_overdue:
                    self._notified_ids.add(str(c.id))
                return

            for commitment in newly_overdue:
                payload = PushPayload(
                    title="Overwatch",
                    body=f"You said you'd: {commitment.text}",
                    tag=str(commitment.id),
                )
                stale = self._push.broadcast(subscriptions, payload)
                for endpoint in stale:
                    sub_repo.delete_by_endpoint(endpoint)
                self._notified_ids.add(str(commitment.id))
                logger.info(
                    f"ReminderScheduler: pushed reminder for '{commitment.text[:40]}'"
                )
        finally:
            conn.close()
