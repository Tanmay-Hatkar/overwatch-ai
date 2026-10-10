"""
main.py — FastAPI application entry point for Overwatch backend.

Run with:
    uvicorn app.main:app --reload

The --reload flag auto-restarts the server on file changes (dev only).

Production responsibilities (besides routing):
  - Configure logging (level + format) at startup
  - Mount CORS middleware for running the mobile app in a browser
    (`expo start --web`); the native app itself isn't subject to CORS
  - Start the StaleCheckScheduler in the FastAPI lifespan
"""

import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import cors_origin_list, settings
from app.database import init_db
from app.routes import auth, briefings, calendar, chat, commitments, reflections
from app.services.stale_check_scheduler import StaleCheckScheduler


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

# Module-level scheduler holder — lifespan populates it on startup.
_stale_scheduler: StaleCheckScheduler | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """
    Lifespan context — startup before yield, shutdown after.

    Responsibilities:
      1. Initialize the SQLite schema (idempotent — runs all migrations).
      2. Start the StaleCheckScheduler background task, which asks (once,
         ever) about open commitments that have gone quiet.

    Due-time reminders are scheduled on the device by the mobile app
    (expo-notifications + ring alarm), so there is no server-side
    reminder scheduler.
    """
    global _stale_scheduler

    logger.info(
        "Starting Overwatch backend (environment=%s, db=%s)",
        settings.environment,
        settings.database_path or "<default>",
    )
    init_db()

    _stale_scheduler = StaleCheckScheduler()
    _stale_scheduler.start()

    yield

    if _stale_scheduler is not None:
        await _stale_scheduler.stop()


app = FastAPI(
    title="Overwatch",
    description="A conversational AI that captures the commitments you make to yourself.",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — only relevant when the mobile app runs in a browser via Expo web
# (local dev, screenshots). Native fetches aren't subject to CORS. Auth is a
# bearer header, never a cookie, so credentials aren't needed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origin_list(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

# Commitments — CRUD + natural language parsing
app.include_router(commitments.router)

# Briefings — daily LLM-generated summary with cache
app.include_router(briefings.router)

# Reflections — evening LLM-generated look-back with cache
app.include_router(reflections.router)

# Calendar — events from the configured CalendarProvider
# (auto-detected: token.json present → Google, else Mock)
app.include_router(calendar.router)

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
