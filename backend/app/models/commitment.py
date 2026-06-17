"""
commitment.py — Pydantic schemas for the Commitment domain entity.

A Commitment is the core primitive of Overwatch:
  "Something the user said they'd do, by some time."

Multiple schemas exist because the API exposes different shapes for
different operations:

  CommitmentBase     - shared fields (text, due_at)
  CommitmentCreate   - what POST /commitments accepts
  CommitmentUpdate   - what PATCH /commitments/{id} accepts (all fields optional)
  CommitmentResponse - what the API returns (adds id, status, timestamps)

This separation is a standard pattern: request schemas and response schemas
are different because the server fills in fields the client never sends
(id, created_at, etc.).
"""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CommitmentStatus(str, Enum):
    """All valid states for a Commitment."""

    OPEN = "open"
    DONE = "done"
    ABANDONED = "abandoned"


class Recurrence(str, Enum):
    """How often a commitment repeats. NONE = a one-off."""

    NONE = "none"
    DAILY = "daily"
    WEEKLY = "weekly"


class CommitmentBase(BaseModel):
    """
    Fields shared between input and output schemas.

    Used as a base class for CommitmentCreate and CommitmentResponse.
    Inheritance avoids repeating field definitions.
    """

    text: str = Field(
        ...,  # required
        min_length=1,
        max_length=500,
        description="What the user said they'd do.",
    )
    due_at: datetime | None = Field(
        default=None,
        description="Optional timestamp for when the commitment is due.",
    )
    recurrence: Recurrence = Field(
        default=Recurrence.NONE,
        description="How often it repeats. When completed, a recurring item rolls forward.",
    )
    reminder_lead_minutes: int = Field(
        default=0,
        ge=0,
        le=1440,  # at most 24h before
        description=(
            "How many minutes BEFORE due_at to nudge. 0 = fire exactly at the "
            "time (an alarm, e.g. 'wake me at 2pm'). >0 = a heads-up that many "
            "minutes before (e.g. a meeting). Set by the user's phrasing; "
            "editable per item."
        ),
    )
    group_name: str = Field(
        default="",
        max_length=60,
        description=(
            "Optional group/section the commitment belongs to (e.g. 'Groceries', "
            "'Work', 'Overwatch'). Empty = ungrouped. Used to organize the list."
        ),
    )


class CommitmentCreate(CommitmentBase):
    """
    Schema for creating a new Commitment via POST /commitments.

    Inherits text and due_at from CommitmentBase.
    Server fills in id, status='open', created_at, updated_at.
    """

    # Empty body — all needed fields come from CommitmentBase.
    pass


class CommitmentUpdate(BaseModel):
    """
    Schema for partial updates via PATCH /commitments/{id}.

    Every field is optional — clients send only the fields they want to change.
    Does NOT inherit from CommitmentBase because CommitmentBase has required
    fields (text), but for PATCH everything must be optional.
    """

    text: str | None = Field(default=None, min_length=1, max_length=500)
    due_at: datetime | None = None
    status: CommitmentStatus | None = None
    recurrence: Recurrence | None = None
    reminder_lead_minutes: int | None = Field(default=None, ge=0, le=1440)
    group_name: str | None = Field(default=None, max_length=60)


class CommitmentResponse(CommitmentBase):
    """
    Schema for API responses. Adds server-managed fields on top of the base.

    Used as the response_model for any endpoint that returns a commitment.
    """

    id: UUID
    status: CommitmentStatus
    created_at: datetime
    updated_at: datetime

    # Allow Pydantic to construct this model from objects with matching
    # attributes (not just dicts). Useful when converting from a dataclass
    # or DB row object to a response.
    model_config = ConfigDict(from_attributes=True)


class CommitmentParseRequest(BaseModel):
    """
    Schema for POST /commitments/parse.

    The user sends a natural language message; the server uses an LLM to
    extract text + due_at and creates the commitment.
    """

    message: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Free-form natural language describing the commitment.",
    )
