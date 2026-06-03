"""
main.py — FastAPI application entry point for Overwatch backend.

Run with:
    uvicorn app.main:app --reload

The --reload flag auto-restarts the server on file changes (dev only).
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import init_db
from app.routes import briefings, calendar, commitments, push, stats
from app.routes.push import get_push_service
from app.services.reminder_scheduler import ReminderScheduler

logger = logging.getLogger(__name__)

# Module-level scheduler holder — lifespan populates it on startup,
# accessor below returns it for FastAPI dependencies.
_scheduler: ReminderScheduler | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """
    Lifespan context — startup before yield, shutdown after.

    Responsibilities:
      1. Initialize the SQLite schema (idempotent).
      2. Start the ReminderScheduler background task, which polls
         commitments and fires push notifications when items become due.
    """
    global _scheduler

    init_db()

    push_service = get_push_service()
    if push_service.is_configured:
        _scheduler = ReminderScheduler(push_service)
        _scheduler.start()
    else:
        logger.info(
            "VAPID not configured — skipping ReminderScheduler. "
            "Set VAPID_PRIVATE_KEY to enable push notifications."
        )

    yield

    if _scheduler is not None:
        await _scheduler.stop()


app = FastAPI(
    title="Overwatch",
    description="A conversational AI that captures the commitments you make to yourself.",
    version="0.1.0",
    lifespan=lifespan,
)

# Commitments — CRUD + natural language parsing
app.include_router(commitments.router)

# Briefings — daily LLM-generated summary with cache
app.include_router(briefings.router)

# Stats — completion counts, streak, 7-day series
app.include_router(stats.router)

# Calendar — events from the configured CalendarProvider
# (auto-detected: token.json present → Google, else Mock)
app.include_router(calendar.router)

# Push — subscribe/unsubscribe + test broadcast for Web Push notifications
app.include_router(push.router)


@app.get("/health")
def health() -> dict[str, str]:
    """
    Health check endpoint.

    Returns:
        A dict with status='ok' if the server is running.
    """
    return {"status": "ok"}
