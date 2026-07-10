"""
test_chat_service.py — Unit tests for ChatService.

The LLM is mocked at the import site in chat_service. Tests cover the
three intent branches (add_commitment / query / general), JSON parsing
robustness, error paths, and that add_commitment actually creates a row.
"""

import json
from uuid import uuid4
from datetime import UTC, date, datetime, timedelta
from unittest.mock import patch

import pytest

from app.models.chat import ChatRequest, ChatTurn
from app.models.commitment import CommitmentCreate, CommitmentStatus
from app.providers.mock_calendar_provider import MockCalendarProvider
from app.services.calendar_service import CalendarService
from app.services.chat_service import ChatError, ChatService
from app.services.commitment_service import CommitmentService

LLM_PATCH = "app.services.chat_service.call_llm"

UID = uuid4()


@pytest.fixture
def chat_service(service: CommitmentService) -> ChatService:
    """ChatService wired to the in-memory CommitmentService + mock calendar."""
    return ChatService(service, CalendarService(MockCalendarProvider()))


def _llm_response(intent: str, **fields) -> str:
    """Helper to build the JSON the LLM is expected to return."""
    payload = {"intent": intent, "text": None, "due_at": None, "reply": "default reply"}
    payload.update(fields)
    return json.dumps(payload)


# ---------------------------------------------------------------------------
# add_commitment intent
# ---------------------------------------------------------------------------


def test_reminder_lead_minutes_threaded_from_llm(chat_service: ChatService) -> None:
    """A heads-up lead (e.g. a meeting) flows from the LLM onto the commitment."""
    fake = _llm_response(
        "add_commitment",
        text="Client meeting",
        due_at="2026-06-04T14:00:00",
        reminder_lead_minutes=15,
        reply="Got it — heads-up 15 min before.",
    )
    with patch(LLM_PATCH, return_value=fake):
        result = chat_service.handle(UID, ChatRequest(message="client meeting at 2pm"))

    assert result.commitment is not None
    assert result.commitment.reminder_lead_minutes == 15


def test_reminder_lead_defaults_to_zero_for_alarms(chat_service: ChatService) -> None:
    """An alarm-style commitment (no lead given) stays at 0 = fire exactly at time."""
    fake = _llm_response(
        "add_commitment",
        text="Wake up",
        due_at="2026-06-04T06:30:00",
        reply="Alarm set.",
    )
    with patch(LLM_PATCH, return_value=fake):
        result = chat_service.handle(UID, ChatRequest(message="wake me at 6:30"))

    assert result.commitment is not None
    assert result.commitment.reminder_lead_minutes == 0


def test_add_commitment_creates_record_and_returns_it(chat_service: ChatService) -> None:
    """add_commitment intent persists the commitment and includes it in the response."""
    fake = _llm_response(
        "add_commitment",
        text="Call mom",
        due_at="2026-06-04T15:00:00",
        reply="Got it — calling mom Thursday at 3pm.",
    )
    with patch(LLM_PATCH, return_value=fake):
        result = chat_service.handle(UID, ChatRequest(message="call mom tomorrow at 3pm"))

    assert result.intent == "add_commitment"
    assert result.commitment is not None
    assert result.commitment.text == "Call mom"
    assert result.commitment.due_at is not None
    assert result.commitment.due_at.hour == 15
    assert "calling mom" in result.reply.lower()


def test_add_commitment_with_null_due_at(chat_service: ChatService) -> None:
    """No due_at means a floating commitment — still gets created."""
    fake = _llm_response(
        "add_commitment",
        text="Clean my room",
        due_at=None,
        reply="OK, clean your room — added.",
    )
    with patch(LLM_PATCH, return_value=fake):
        result = chat_service.handle(UID, ChatRequest(message="add a task to clean my room"))

    assert result.commitment is not None
    assert result.commitment.due_at is None


def test_add_commitment_skips_create_when_text_missing(chat_service: ChatService) -> None:
    """LLM classifies as add_commitment but provides no text → don't create, just reply."""
    fake = _llm_response("add_commitment", text=None, reply="Sure — what should I add?")
    with patch(LLM_PATCH, return_value=fake):
        result = chat_service.handle(UID, ChatRequest(message="add a task"))

    assert result.intent == "add_commitment"
    assert result.commitment is None  # nothing persisted
    assert result.reply  # but we still get a reply


def test_multi_add_creates_all_items(
    chat_service: ChatService, service: CommitmentService
) -> None:
    """When the LLM returns `items`, every commitment is created."""
    fake = _llm_response(
        "add_commitment",
        items=[
            {"text": "Renew passport", "due_at": None},
            {"text": "Book dentist", "due_at": None},
            {"text": "Email landlord", "due_at": None},
        ],
        reply="Added 3 things to your list.",
    )
    with patch(LLM_PATCH, return_value=fake):
        result = chat_service.handle(UID, ChatRequest(message="passport, dentist, landlord"))

    # The response carries the first for the UI toast...
    assert result.commitment is not None
    assert result.commitment.text == "Renew passport"
    # ...but all three were actually persisted for this user.
    texts = {c.text for c in service.list(UID)}
    assert {"Renew passport", "Book dentist", "Email landlord"} <= texts


def test_multi_add_items_take_precedence_and_skip_blanks(
    chat_service: ChatService, service: CommitmentService
) -> None:
    """`items` wins over top-level text; blank items are skipped, not fatal."""
    fake = _llm_response(
        "add_commitment",
        text="ignored because items present",
        items=[{"text": "Real task", "due_at": None}, {"text": "  ", "due_at": None}],
        reply="Added it.",
    )
    with patch(LLM_PATCH, return_value=fake):
        chat_service.handle(UID, ChatRequest(message="..."))

    texts = [c.text for c in service.list(UID)]
    assert "Real task" in texts
    assert "ignored because items present" not in texts
    assert "" not in texts and "  " not in texts


def test_add_commitment_drops_invalid_due_at(chat_service: ChatService) -> None:
    """A malformed due_at is silently dropped; commitment is still created."""
    fake = _llm_response(
        "add_commitment",
        text="Test commitment",
        due_at="not a real date",
        reply="Added.",
    )
    with patch(LLM_PATCH, return_value=fake):
        result = chat_service.handle(UID, ChatRequest(message="test"))

    assert result.commitment is not None
    assert result.commitment.due_at is None  # invalid date dropped


# ---------------------------------------------------------------------------
# timezone handling
# ---------------------------------------------------------------------------


def test_naive_due_at_interpreted_in_user_timezone(chat_service: ChatService) -> None:
    """
    A naive due_at like '11:00' with a Toronto timezone (UTC-4 in June) is
    stored as 15:00 UTC — so reminders fire at the right absolute instant.
    """
    fake = _llm_response(
        "add_commitment",
        text="Vosyn meeting",
        due_at="2026-06-08T11:00:00",
        reply="Got it.",
    )
    with patch(LLM_PATCH, return_value=fake):
        result = chat_service.handle(
            UID, ChatRequest(message="meeting at 11am Monday", timezone="America/Toronto")
        )

    assert result.commitment is not None
    assert result.commitment.due_at is not None
    # 11:00 America/Toronto (EDT, UTC-4) == 15:00 UTC
    assert result.commitment.due_at.astimezone(UTC).hour == 15


def test_missing_timezone_falls_back_to_utc(chat_service: ChatService) -> None:
    """No timezone supplied → naive due_at is treated as UTC (no shift)."""
    fake = _llm_response(
        "add_commitment",
        text="Test",
        due_at="2026-06-08T11:00:00",
        reply="Added.",
    )
    with patch(LLM_PATCH, return_value=fake):
        result = chat_service.handle(UID, ChatRequest(message="x"))

    assert result.commitment is not None
    assert result.commitment.due_at is not None
    assert result.commitment.due_at.astimezone(UTC).hour == 11


def test_invalid_timezone_falls_back_gracefully(chat_service: ChatService) -> None:
    """A garbage timezone name doesn't crash — falls back to UTC."""
    fake = _llm_response("general", reply="Hey.")
    with patch(LLM_PATCH, return_value=fake):
        result = chat_service.handle(
            UID, ChatRequest(message="hi", timezone="Not/AReal_Zone")
        )

    assert result.intent == "general"  # handled without error


# ---------------------------------------------------------------------------
# query intent
# ---------------------------------------------------------------------------


def test_query_intent_does_not_create_anything(chat_service: ChatService) -> None:
    """query intent just returns a reply — no side effects."""
    fake = _llm_response(
        "query",
        reply="You have nothing on your plate today.",
    )
    with patch(LLM_PATCH, return_value=fake):
        result = chat_service.handle(UID, ChatRequest(message="what do I have today?"))

    assert result.intent == "query"
    assert result.commitment is None
    assert "nothing" in result.reply.lower()


def test_clarify_intent_creates_nothing(
    chat_service: ChatService, service: CommitmentService
) -> None:
    """A clarify intent (missing/vague info) asks a question and persists nothing."""
    fake = _llm_response(
        "clarify",
        reply="Sure — what time, and how long should I block?",
    )
    with patch(LLM_PATCH, return_value=fake):
        result = chat_service.handle(UID, ChatRequest(message="add a team meeting tomorrow"))

    assert result.intent == "clarify"
    assert result.commitment is None
    assert "?" in result.reply           # it's a question
    assert service.list(UID) == []       # nothing junk was created


def test_query_intent_prompt_includes_current_state(
    chat_service: ChatService, service: CommitmentService
) -> None:
    """The user prompt includes open + overdue commitments for the LLM to reason over."""
    from app.models.commitment import CommitmentCreate

    today_noon = datetime.combine(date.today(), datetime.min.time().replace(hour=12), tzinfo=UTC)
    yesterday = datetime.now(UTC) - timedelta(days=1)
    service.create(UID, CommitmentCreate(text="Lunch with Alex", due_at=today_noon))
    service.create(UID, CommitmentCreate(text="Update docs", due_at=yesterday))

    fake = _llm_response("query", reply="checked.")
    with patch(LLM_PATCH, return_value=fake) as mock:
        chat_service.handle(UID, ChatRequest(message="what's on my plate?"))

    user_prompt = mock.call_args.kwargs["user_prompt"]
    assert "Lunch with Alex" in user_prompt
    assert "Update docs" in user_prompt


# ---------------------------------------------------------------------------
# general intent
# ---------------------------------------------------------------------------


def test_general_intent_just_replies(chat_service: ChatService) -> None:
    """general intent is small talk — no creation, no DB write."""
    fake = _llm_response("general", reply="Hey. What's on your mind?")
    with patch(LLM_PATCH, return_value=fake):
        result = chat_service.handle(UID, ChatRequest(message="hi"))

    assert result.intent == "general"
    assert result.commitment is None
    assert result.reply == "Hey. What's on your mind?"


# ---------------------------------------------------------------------------
# Conversation history
# ---------------------------------------------------------------------------


def test_history_is_injected_into_prompt(chat_service: ChatService) -> None:
    """The recent conversation turns appear in the user prompt as context."""
    history = [
        ChatTurn(role="user", content="I'm planning my week"),
        ChatTurn(role="assistant", content="Tell me what's on it."),
    ]
    fake = _llm_response("general", reply="OK.")
    with patch(LLM_PATCH, return_value=fake) as mock:
        chat_service.handle(
            UID, ChatRequest(message="actually, add a meeting for Tuesday", history=history)
        )

    user_prompt = mock.call_args.kwargs["user_prompt"]
    assert "planning my week" in user_prompt
    assert "what's on it" in user_prompt


# ---------------------------------------------------------------------------
# Robustness — LLM output quirks
# ---------------------------------------------------------------------------


def test_strips_markdown_code_fences(chat_service: ChatService) -> None:
    """LLM wrapping JSON in ```json ... ``` is tolerated."""
    fake = (
        '```json\n'
        + _llm_response("general", reply="Hi.")
        + '\n```'
    )
    with patch(LLM_PATCH, return_value=fake):
        result = chat_service.handle(UID, ChatRequest(message="hi"))
    assert result.reply == "Hi."


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_raises_when_llm_unavailable(chat_service: ChatService) -> None:
    """call_llm returning None bubbles up as ChatError."""
    with patch(LLM_PATCH, return_value=None):
        with pytest.raises(ChatError, match="unavailable"):
            chat_service.handle(UID, ChatRequest(message="hi"))


def test_raises_on_invalid_json(chat_service: ChatService) -> None:
    """Non-JSON LLM output → ChatError."""
    with patch(LLM_PATCH, return_value="this is plainly not JSON"):
        with pytest.raises(ChatError, match="not valid JSON"):
            chat_service.handle(UID, ChatRequest(message="hi"))


def test_raises_on_missing_required_fields(chat_service: ChatService) -> None:
    """JSON missing 'intent' or 'reply' → ChatError."""
    with patch(LLM_PATCH, return_value='{"foo": "bar"}'):
        with pytest.raises(ChatError):
            chat_service.handle(UID, ChatRequest(message="hi"))


def test_raises_on_invalid_intent_value(chat_service: ChatService) -> None:
    """An intent value outside the allowed set → ChatError (Pydantic validation)."""
    fake = json.dumps(
        {"intent": "delete_my_account", "text": None, "due_at": None, "reply": "no"}
    )
    with patch(LLM_PATCH, return_value=fake):
        with pytest.raises(ChatError):
            chat_service.handle(UID, ChatRequest(message="hi"))


# ---------------------------------------------------------------------------
# stale-check reply interception (ADR-0017)
# ---------------------------------------------------------------------------


def _stale_llm_response(outcome: str, **fields) -> str:
    """Helper to build the JSON the stale-check classifier is expected to return."""
    payload = {"outcome": outcome, "new_due_at": None, "reply": "OK."}
    payload.update(fields)
    return json.dumps(payload)


def test_no_pending_check_leaves_normal_flow_unchanged(chat_service: ChatService) -> None:
    """With no pending stale check-in, handle() behaves exactly as before —
    exactly one (normal) LLM call."""
    fake = _llm_response("general", reply="Hi there.")
    with patch(LLM_PATCH, return_value=fake) as mock:
        result = chat_service.handle(UID, ChatRequest(message="hi"))

    assert result.intent == "general"
    mock.assert_called_once()


def test_pending_check_still_valid_short_circuits_normal_flow(
    chat_service: ChatService, service: CommitmentService
) -> None:
    """A 'still_valid' reply is handled entirely by the stale-check
    classifier — the normal add/query/general LLM call never runs."""
    c = service.create(UID, CommitmentCreate(text="Finish the deck", due_at=None))
    service.mark_stale_check_sent(UID, c.id)

    fake = _stale_llm_response("still_valid", reply="Good to know — still on the list.")
    with patch(LLM_PATCH, return_value=fake) as mock:
        result = chat_service.handle(UID, ChatRequest(message="yeah still doing it"))

    assert result.intent == "general"
    assert result.reply == "Good to know — still on the list."
    mock.assert_called_once()  # one LLM call total (the stale-check classifier)

    # No longer pending — this only ever fires once.
    assert service.list_pending_stale_checks(UID) == []
    # The plan itself is unchanged.
    assert service.get(UID, c.id).status == CommitmentStatus.OPEN


def test_pending_check_abandon_updates_status(
    chat_service: ChatService, service: CommitmentService
) -> None:
    """An 'abandon' reply marks the commitment abandoned — a choice the
    user made, not a deletion, not a failure."""
    c = service.create(UID, CommitmentCreate(text="Call the dentist", due_at=None))
    service.mark_stale_check_sent(UID, c.id)

    fake = _stale_llm_response("abandon", reply="Got it — letting that one go.")
    with patch(LLM_PATCH, return_value=fake):
        result = chat_service.handle(UID, ChatRequest(message="nah don't need to anymore"))

    assert result.reply == "Got it — letting that one go."
    assert service.get(UID, c.id).status == CommitmentStatus.ABANDONED
    assert service.list_pending_stale_checks(UID) == []


def test_pending_check_reschedule_updates_due_at(
    chat_service: ChatService, service: CommitmentService
) -> None:
    """A 'reschedule' reply moves due_at to the new time, resolved in the
    user's timezone (same helper the normal add_commitment path uses)."""
    c = service.create(UID, CommitmentCreate(text="Finish the deck", due_at=None))
    service.mark_stale_check_sent(UID, c.id)

    fake = _stale_llm_response(
        "reschedule", new_due_at="2026-07-10T17:00:00", reply="Moved to tomorrow at 5pm."
    )
    with patch(LLM_PATCH, return_value=fake):
        result = chat_service.handle(
            UID, ChatRequest(message="yeah but tomorrow at 5pm now", timezone="America/Toronto")
        )

    assert result.reply == "Moved to tomorrow at 5pm."
    updated = service.get(UID, c.id)
    assert updated.due_at is not None
    # 17:00 America/Toronto (EDT, UTC-4) == 21:00 UTC
    assert updated.due_at.astimezone(UTC).hour == 21
    assert service.list_pending_stale_checks(UID) == []


def test_pending_check_reschedule_without_new_time_leaves_due_at_unchanged(
    chat_service: ChatService, service: CommitmentService
) -> None:
    """If the classifier can't extract a new time, we never guess one —
    due_at is left as-is (still acknowledged so it isn't re-intercepted)."""
    c = service.create(UID, CommitmentCreate(text="Finish the deck", due_at=None))
    service.mark_stale_check_sent(UID, c.id)

    fake = _stale_llm_response("reschedule", new_due_at=None, reply="No problem — when though?")
    with patch(LLM_PATCH, return_value=fake):
        chat_service.handle(UID, ChatRequest(message="gonna move it but not sure when"))

    assert service.get(UID, c.id).due_at is None
    assert service.list_pending_stale_checks(UID) == []


def test_pending_check_unrelated_falls_through_to_normal_flow(
    chat_service: ChatService, service: CommitmentService
) -> None:
    """An 'unrelated' reply acknowledges the check-in but still runs the
    normal chat pipeline for the SAME message (two LLM calls total)."""
    c = service.create(UID, CommitmentCreate(text="Finish the deck", due_at=None))
    service.mark_stale_check_sent(UID, c.id)

    stale_fake = _stale_llm_response("unrelated", reply="")
    normal_fake = _llm_response("general", reply="Sure, tell me more.")

    with patch(LLM_PATCH, side_effect=[stale_fake, normal_fake]) as mock:
        result = chat_service.handle(UID, ChatRequest(message="also remind me to call mom later"))

    assert mock.call_count == 2
    assert result.intent == "general"
    assert result.reply == "Sure, tell me more."
    # The check-in is no longer pending even though the reply was unrelated —
    # we don't keep re-intercepting future messages waiting for an answer.
    assert service.list_pending_stale_checks(UID) == []
    assert service.get(UID, c.id).status == CommitmentStatus.OPEN


def test_multiple_pending_checks_all_acknowledged_by_one_reply(
    chat_service: ChatService, service: CommitmentService
) -> None:
    """When several check-ins are pending at once, a single reply resolves
    all of them in one dedicated LLM call."""
    a = service.create(UID, CommitmentCreate(text="Finish the deck", due_at=None))
    b = service.create(UID, CommitmentCreate(text="Call the plumber", due_at=None))
    service.mark_stale_check_sent(UID, a.id)
    service.mark_stale_check_sent(UID, b.id)

    fake = _stale_llm_response("still_valid", reply="Both still on — good to know.")
    with patch(LLM_PATCH, return_value=fake) as mock:
        result = chat_service.handle(UID, ChatRequest(message="yeah both still happening"))

    assert result.reply == "Both still on — good to know."
    mock.assert_called_once()
    assert service.list_pending_stale_checks(UID) == []


def test_pending_check_llm_unavailable_leaves_it_pending_and_falls_through(
    chat_service: ChatService, service: CommitmentService
) -> None:
    """If the stale-check classifier call itself fails (LLM unavailable),
    we don't lose the pending state — it falls through to the normal
    pipeline for this message and stays pending for a future reply."""
    c = service.create(UID, CommitmentCreate(text="Finish the deck", due_at=None))
    service.mark_stale_check_sent(UID, c.id)

    normal_fake = _llm_response("general", reply="Hey.")
    with patch(LLM_PATCH, side_effect=[None, normal_fake]) as mock:
        result = chat_service.handle(UID, ChatRequest(message="hi"))

    assert mock.call_count == 2
    assert result.reply == "Hey."
    # Still pending — we'll try to interpret the next message as a reply too.
    assert len(service.list_pending_stale_checks(UID)) == 1
