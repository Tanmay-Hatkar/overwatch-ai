"""
main.py — FastAPI application entry point for Overwatch backend.

Run with:
    uvicorn app.main:app --reload

The --reload flag auto-restarts the server on file changes (dev only).
"""

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI

from app.database import init_db
from app.routes import briefings, commitments


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """
    Lifespan context — code that runs at app startup (before yield)
    and shutdown (after yield).

    The `_app` parameter is required by FastAPI's lifespan contract but
    isn't used here. The underscore prefix signals intentional non-use.

    Used to initialize the database schema once on startup.
    """
    # Startup
    init_db()
    yield
    # Shutdown — nothing to clean up yet


app = FastAPI(
    title="Overwatch",
    description="A conversational AI that captures the commitments you make to yourself.",
    version="0.1.0",
    lifespan=lifespan,
)

# Mount the commitments router. All routes defined in app/routes/commitments.py
# become available under /commitments.
app.include_router(commitments.router)

# Mount the briefings router. All routes defined in app/routes/briefings.py
# become available under /briefings.
app.include_router(briefings.router)


@app.get("/health")
def health() -> dict[str, str]:
    """
    Health check endpoint.

    Returns:
        A dict with status='ok' if the server is running.
    """
    return {"status": "ok"}
