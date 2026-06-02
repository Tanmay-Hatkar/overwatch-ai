"""
event.py — Pydantic schemas for calendar events.

Events come from external providers (Google, Outlook, etc.) via the
CalendarProvider interface. We never persist them in our DB — they are
always read fresh from the source. This avoids sync conflicts and
stale-data bugs.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class CalendarEvent(BaseModel):
    """One event from an external calendar."""

    id: str = Field(..., description="Provider's native event id")
    source: str = Field(..., description='Provider tag, e.g., "google" or "mock"')
    title: str = Field(..., description="Event title / summary")
    start_at: datetime = Field(..., description="Start time (tz-aware UTC)")
    end_at: datetime = Field(..., description="End time (tz-aware UTC)")
    all_day: bool = Field(default=False, description="True for all-day events")
    location: str | None = Field(default=None, description="Physical or virtual location")
    description: str | None = Field(default=None, description="Free-form description / agenda")
    meeting_url: str | None = Field(
        default=None,
        description="Extracted Zoom/Meet/Teams URL if present in the event",
    )
    color: str | None = Field(
        default=None,
        description="Provider-supplied color hint (hex string). UI can use a default.",
    )
