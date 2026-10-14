"""
chat.py — Pydantic schemas for the conversational chat endpoint.

The frontend sends a user message + the recent conversation history.
The backend classifies intent, takes an action (e.g., create a commitment,
look up today's plan), and returns a natural-language reply plus optional
structured action metadata so the UI can update.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.commitment import CommitmentResponse
from app.models.goal import GoalResponse

# Intents the chat router can classify a message into.
ChatIntent = Literal[
    "add_commitment",
    "query",
    "modify_commitment",  # edits an EXISTING open commitment (reschedule, retitle, recurrence)
    "clarify",   # needs more info before it can act — asks a question, creates nothing
    "general",
    "add_goal",  # a count-per-week target: "10 applications this week" (ADR-0026)
    "log_goal",  # progress toward an existing goal: "applied to 2 more"
    "close_commitment",  # finish / drop / delete existing commitment(s) (ADR-0027)
]

# For intent='close_commitment': what happens to the target(s). 'done' and
# 'abandoned' are status changes (a recurring item marked done rolls forward,
# same as the checkbox); 'deleted' is a hard delete, only on an explicit ask.
CloseAction = Literal["done", "abandoned", "deleted"]


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
    timezone: str | None = Field(
        default=None,
        max_length=64,
        description=(
            "The user's IANA timezone name (e.g. 'America/Toronto'), sent by "
            "the browser. Used so the assistant computes 'today', 'tonight', "
            "and relative times against the user's local clock — not the "
            "server's. When absent or invalid, the server falls back to UTC."
        ),
    )


# For intent='clarify': what kind of follow-up this is, so the client can
# render a purpose-built widget (time picker / quick-reply chips) instead
# of a plain text bubble the user has to type a free-text answer into.
# 'open' is the fallback when nothing more specific fits — same as today's
# behavior, a normal reply bubble expecting a free-text answer.
ClarifyKind = Literal["time", "duration", "confirm_recurring", "confirm_target", "open"]


class ChatResponse(BaseModel):
    """Response body for POST /chat."""

    reply: str = Field(..., description="The assistant's natural-language reply.")
    intent: ChatIntent = Field(..., description="What the assistant classified the message as.")
    commitment: CommitmentResponse | None = Field(
        default=None,
        description=(
            "If intent='add_commitment', the created commitment record. "
            "If intent='modify_commitment', the updated commitment record."
        ),
    )
    closed: list[CommitmentResponse] | None = Field(
        default=None,
        description=(
            "If intent='close_commitment', each commitment that was closed, "
            "as it was just before closing (a deleted one no longer exists). "
            "None when nothing could be applied."
        ),
    )
    close_action: CloseAction | None = Field(
        default=None,
        description="If intent='close_commitment', what was done to `closed`.",
    )
    goal: GoalResponse | None = Field(
        default=None,
        description=(
            "If intent='add_goal' or 'log_goal', the goal after the change, "
            "with this week's progress."
        ),
    )
    clarify_kind: ClarifyKind | None = Field(
        default=None,
        description=(
            "Only set when intent='clarify'. Tells the client what kind of "
            "follow-up UI to render. 'confirm_recurring'/'confirm_target'/"
            "'duration' pair with clarify_options for tap-only quick-reply "
            "chips (and 'time' may too, for a small fixed set of likely "
            "candidates); 'open', or any of those without clarify_options, "
            "falls back to a normal free-text reply bubble. There's no "
            "dedicated native time/duration picker widget — free text (typed "
            "or via a chip) is the only input path today."
        ),
    )
    clarify_options: list[str] | None = Field(
        default=None,
        max_length=4,
        description=(
            "Tap-only quick-reply chips, whichever clarify_kind they're "
            "attached to (typically 'confirm_recurring', 'confirm_target', or "
            "'duration'; occasionally 'time' with a small fixed set of likely "
            "candidates, e.g. ['Today', 'Tomorrow']). Each option, tapped, is "
            "sent verbatim as the next chat message — no new endpoint needed. "
            "None/empty means no chips — the client falls back to a normal "
            "free-text reply bubble regardless of clarify_kind."
        ),
    )

    model_config = ConfigDict(from_attributes=True)


class CommitmentDraft(BaseModel):
    """One extracted commitment within a multi-add turn."""

    text: str
    due_at: str | None = None  # ISO 8601 datetime or null
    recurrence: str | None = None  # 'daily' | 'weekly' | 'none' / null
    # Minutes before due_at to nudge: 0 = exact (alarm), >0 = heads-up.
    reminder_lead_minutes: int = 0
    # Natural-recall check-in line (ADR-0021), generated in the same call.
    reminder_phrase: str | None = None


# Internal-only schema for what the LLM returns when classifying
class _ChatIntentResult(BaseModel):
    """Parsed structured output from the LLM's intent-classification call."""

    intent: ChatIntent
    # For a SINGLE add_commitment, the LLM fills text + due_at (+ recurrence).
    # For modify_commitment, only the field(s) actually changing are non-null.
    text: str | None = None
    due_at: str | None = None  # ISO 8601 datetime or null
    recurrence: str | None = None  # 'daily' | 'weekly' | 'none' / null
    # Minutes before due_at to nudge: 0 = exact (alarm), >0 = heads-up.
    reminder_lead_minutes: int | None = 0
    # Natural-recall check-in line (ADR-0021). For add_commitment, always
    # set. For modify_commitment, only set (regenerated) when text/due_at
    # changed — see chat.py's prompt rules.
    reminder_phrase: str | None = None
    # For MULTIPLE commitments in one message, the LLM fills items instead.
    # When present (non-empty), it takes precedence over text/due_at.
    items: list[CommitmentDraft] | None = None
    # Only meaningful when intent='modify_commitment' — which existing open
    # commitment (by id, drawn from the "Editable commitments" context
    # block) this message edits.
    target_commitment_id: str | None = None
    # close_commitment (ADR-0027): one or more ids from the same block, and
    # what to do with them.
    target_commitment_ids: list[str] | None = None
    close_action: CloseAction | None = None
    # add_goal / log_goal (ADR-0026). target_goal_id comes from the "Weekly
    # goals" context block: for log_goal it names the goal being counted;
    # for add_goal it's set only when re-targeting an existing goal.
    goal_text: str | None = None
    target_count: int | None = None
    target_goal_id: str | None = None
    amount: int | None = None
    reply: str  # Always; the natural-language acknowledgment / answer / chat
    # Only meaningful when intent='clarify' — see ClarifyKind/ChatResponse.
    clarify_kind: ClarifyKind | None = None
    clarify_options: list[str] | None = None
