"""
stale_check.py — Internal schema for the stale-plan check-in reply classifier.

When a user replies to a pending "still the plan?" check-in
(StaleCheckScheduler), ChatService runs one small dedicated LLM call to
classify the reply before the normal chat pipeline runs. See
app/prompts/stale_check_reply.py for the prompt and
app/services/chat_service.py for how the result is applied.
"""

from typing import Literal

from pydantic import BaseModel


class _StaleCheckReplyResult(BaseModel):
    """Parsed structured output from the stale-check reply classification call."""

    outcome: Literal["still_valid", "abandon", "reschedule", "unrelated"]
    # ISO 8601 'YYYY-MM-DDTHH:MM:SS' (local, no offset) or null. Only
    # meaningful when outcome == "reschedule".
    new_due_at: str | None = None
    # Natural-language acknowledgment shown to the user. Unused (may be
    # empty) when outcome == "unrelated" — that message is instead handled
    # by the normal chat pipeline, which produces its own reply.
    reply: str = ""
