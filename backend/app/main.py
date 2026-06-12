"""
main.py — FastAPI application entry point for Overwatch backend.

Run with:
    uvicorn app.main:app --reload

The --reload flag auto-restarts the server on file changes (dev only).

Production responsibilities (besides routing):
  - Configure logging (level + format) at startup
  - Mount CORS middleware so the Vercel-hosted frontend can call this API
    when they sit on different origins
  - Start the ReminderScheduler in the FastAPI lifespan
"""

import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import cors_origin_list, settings
from app.database import init_db
from app.routes import auth, briefings, calendar, chat, commitments, push, stats
from app.routes.push import get_push_service
from app.services.reminder_scheduler import ReminderScheduler


def _configure_logging() -> None:
    """
    Set the root logger level and format from settings.

    In production (settings.environment == "production"), uses a single-line
    format that plays nicely with log aggregators (Railway's log viewer,
    Datadog, etc.). In dev, prefers the readable multi-field format.
    """
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    if settings.environment == "production":
        fmt = "%(asctime)s %(levelname)s %(name)s %(message)s"
    else:
        fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(level=level, format=fmt, stream=sys.stdout, force=True)


_configure_logging()
logger = logging.getLogger(__name__)

# Module-level scheduler holder — lifespan populates it on startup,
# accessor below returns it for FastAPI dependencies.
_scheduler: ReminderScheduler | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """
    Lifespan context — startup before yield, shutdown after.

    Responsibilities:
      1. Initialize the SQLite schema (idempotent — runs all migrations).
      2. Start the ReminderScheduler background task, which polls
         commitments and fires push notifications when items become due.
    """
    global _scheduler

    logger.info(
        "Starting Overwatch backend (environment=%s, db=%s)",
        settings.environment,
        settings.database_path or "<default>",
    )
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

# CORS — the frontend (Vercel) calls the backend (Railway) from a different
# origin in production, so the browser enforces preflight checks. We allow the
# origins listed in CORS_ORIGINS (comma-separated env var) PLUS the fixed
# origins the Capacitor native app serves its webview from. The native app
# uses bearer-token auth (no cookies), but its fetches are still cross-origin
# to the backend, so its origin must be allowed. allow_credentials stays True
# for the cookie-based web client, so no "*" wildcard.
_CAPACITOR_ORIGINS = [
    "https://localhost",      # Android (androidScheme: https, the default)
    "http://localhost",       # Android (androidScheme: http)
    "capacitor://localhost",  # iOS
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origin_list() + _CAPACITOR_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
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

# Chat — conversational entry point. POST /chat handles message + history.
app.include_router(chat.router)

# Auth — Google OAuth sign-in + session cookie management.
# Provides /auth/google/login, /auth/google/callback, /auth/me, /auth/logout
# and the `current_user` FastAPI dependency used by other routes for auth-gating.
app.include_router(auth.router)


@app.get("/health")
def health() -> dict[str, str]:
    """
    Health check endpoint.

    Used by Railway's healthcheck pings + by you in a browser to confirm
    the backend is reachable. Returns 200 + {"status":"ok"} when alive.
    """
    return {"status": "ok"}
