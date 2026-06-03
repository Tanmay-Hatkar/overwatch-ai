"""
test_chat_service.py — Unit tests for ChatService.

The LLM is mocked at the import site in chat_service. Tests cover the
three intent branches (add_commitment / query / general), JSON parsing
robustness, error paths, and that add_commitment actually creates a row.
"""

import json
from datetime import UTC, date, datetime, timedelta
from unittest.mock import patch

import pytest

from app.models.chat import ChatRequest, ChatTurn
from app.models.commitment import CommitmentStatus
from app.providers.mock_calendar_provider import MockCalendarProvider
from app.services.calendar_service import CalendarService
from app.services.chat_service import ChatError, ChatService
from app.services.commitment_service import CommitmentService

LLM_PATCH = "app.services.chat_service.call_llm"


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


def test_add_commitment_creates_record_and_returns_it(chat_service: ChatService) -> None:
    """add_commitment intent persists the commitment and includes it in the response."""
    fake = _llm_response(
        "add_commitment",
        text="Call mom",
        due_at="2026-06-04T15:00:00",
        reply="Got it — calling mom Thursday at 3pm.",
    )
    with patch(LLM_PATCH, return_value=fake):
        result = chat_service.handle(ChatRequest(message="call mom tomorrow at 3pm"))

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
        result = chat_service.handle(ChatRequest(message="add a task to clean my room"))

    assert result.commitment is not None
    assert result.commitment.due_at is None


def test_add_commitment_skips_create_when_text_missing(chat_service: ChatService) -> None:
    """LLM classifies as add_commitment but provides no text → don't create, just reply."""
    fake = _llm_response("add_commitment", text=None, reply="Sure — what should I add?")
    with patch(LLM_PATCH, return_value=fake):
        result = chat_service.handle(ChatRequest(message="add a task"))

    assert result.intent == "add_commitment"
    assert result.commitment is None  # nothing persisted
    assert result.reply  # but we still get a reply


def test_add_commitment_drops_invalid_due_at(chat_service: ChatService) -> None:
    """A malformed due_at is silently dropped; commitment is still created."""
    fake = _llm_response(
        "add_commitment",
        text="Test commitment",
        due_at="not a real date",
        reply="Added.",
    )
    with patch(LLM_PATCH, return_value=fake):
        result = chat_service.handle(ChatRequest(message="test"))

    assert result.commitment is not None
    assert result.commitment.due_at is None  # invalid date dropped


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
        result = chat_service.handle(ChatRequest(message="what do I have today?"))

    assert result.intent == "query"
    assert result.commitment is None
    assert "nothing" in result.reply.lower()


def test_query_intent_prompt_includes_current_state(
    chat_service: ChatService, service: CommitmentService
) -> None:
    """The user prompt includes open + overdue commitments for the LLM to reason over."""
    from app.models.commitment import CommitmentCreate

    today_noon = datetime.combine(date.today(), datetime.min.time().replace(hour=12), tzinfo=UTC)
    yesterday = datetime.now(UTC) - timedelta(days=1)
    service.create(CommitmentCreate(text="Lunch with Alex", due_at=today_noon))
    service.create(CommitmentCreate(text="Update docs", due_at=yesterday))

    fake = _llm_response("query", reply="checked.")
    with patch(LLM_PATCH, return_value=fake) as mock:
        chat_service.handle(ChatRequest(message="what's on my plate?"))

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
        result = chat_service.handle(ChatRequest(message="hi"))

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
            ChatRequest(message="actually, add a meeting for Tuesday", history=history)
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
        result = chat_service.handle(ChatRequest(message="hi"))
    assert result.reply == "Hi."


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_raises_when_llm_unavailable(chat_service: ChatService) -> None:
    """call_llm returning None bubbles up as ChatError."""
    with patch(LLM_PATCH, return_value=None):
        with pytest.raises(ChatError, match="unavailable"):
            chat_service.handle(ChatRequest(message="hi"))


def test_raises_on_invalid_json(chat_service: ChatService) -> None:
    """Non-JSON LLM output → ChatError."""
    with patch(LLM_PATCH, return_value="this is plainly not JSON"):
        with pytest.raises(ChatError, match="not valid JSON"):
            chat_service.handle(ChatRequest(message="hi"))


def test_raises_on_missing_required_fields(chat_service: ChatService) -> None:
    """JSON missing 'intent' or 'reply' → ChatError."""
    with patch(LLM_PATCH, return_value='{"foo": "bar"}'):
        with pytest.raises(ChatError):
            chat_service.handle(ChatRequest(message="hi"))


def test_raises_on_invalid_intent_value(chat_service: ChatService) -> None:
    """An intent value outside the allowed set → ChatError (Pydantic validation)."""
    fake = json.dumps(
        {"intent": "delete_my_account", "text": None, "due_at": None, "reply": "no"}
    )
    with patch(LLM_PATCH, return_value=fake):
        with pytest.raises(ChatError):
            chat_service.handle(ChatRequest(message="hi"))
