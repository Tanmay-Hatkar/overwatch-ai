"""
chat.py — Pydantic schemas for the conversational chat endpoint.

The frontend sends a user message + the recent conversation history.
The backend classifies intent, takes an action (e.g., create a commitment,
look up today's plan), and returns a natural-language reply plus optional
structured action metadata so the UI can update.
"""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.commitment import CommitmentResponse


# Intents the chat router can classify a message into.
ChatIntent = Literal[
    "add_commitment",
    "query",
    "general",
]


class ChatTurn(BaseModel):
    """A single past message in the conversation history."""

    role: Literal["user", "assistant"] = Field(..., description="Who said it")
    content: str = Field(..., min_length=1, max_length=2000, description="Message body")


class ChatRequest(BaseModel):
    """Request body for POST /chat."""

    message: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="The latest user message.",
    )
    history: list[ChatTurn] = Field(
        default_factory=list,
        max_length=20,
        description=(
            "Recent conversation turns for context. Most recent last. "
            "Cap to ~10-20 turns; longer histories increase token costs."
        ),
    )


class ChatResponse(BaseModel):
    """Response body for POST /chat."""

    reply: str = Field(..., description="The assistant's natural-language reply.")
    intent: ChatIntent = Field(..., description="What the assistant classified the message as.")
    commitment: CommitmentResponse | None = Field(
        default=None,
        description="If intent='add_commitment', the created commitment record.",
    )

    model_config = ConfigDict(from_attributes=True)


# Internal-only schema for what the LLM returns when classifying
class _ChatIntentResult(BaseModel):
    """Parsed structured output from the LLM's intent-classification call."""

    intent: ChatIntent
    # For add_commitment intents, the LLM also returns the extracted commitment fields
    text: str | None = None
    due_at: str | None = None  # ISO 8601 datetime or null
    reply: str  # Always; the natural-language acknowledgment / answer / chat
