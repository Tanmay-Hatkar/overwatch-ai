"""
test_commitment_parser_service.py — Unit tests for CommitmentParserService.

The LLM is mocked via unittest.mock.patch — we never make real API calls
in tests. Each test sets a stub return value for call_llm to simulate
different LLM behaviors (happy path, malformed JSON, markdown wrapping,
unavailable, etc.).

Strategy: the parser is wired to a REAL CommitmentService backed by an
in-memory SQLite (via the `service` fixture from conftest). So when the
parser succeeds, we actually persist + read back the commitment, which
verifies the full chain works end-to-end.
"""

import json
from datetime import datetime as real_datetime, timezone as dt_timezone
from uuid import uuid4
from unittest.mock import patch

import pytest

from app.models.commitment import CommitmentStatus
from app.services.commitment_parser_service import (
    CommitmentParseError,
    CommitmentParserService,
)
from app.services.commitment_service import CommitmentService

# Where call_llm is bound — we patch the name in the parser's namespace
# (not in the orchestrator module), because the parser imported it
# directly via `from app.agents.orchestrator import call_llm`.
LLM_PATCH_TARGET = "app.services.commitment_parser_service.call_llm"

UID = uuid4()


@pytest.fixture
def parser(service: CommitmentService) -> CommitmentParserService:
    """A parser wired to the in-memory CommitmentService fixture."""
    return CommitmentParserService(service)


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


def test_parses_valid_response_with_due_at(parser: CommitmentParserService) -> None:
    """Standard happy path: LLM returns valid JSON with text + due_at."""
    fake = json.dumps({"text": "Call mom", "due_at": "2026-05-17T15:00:00"})
    with patch(LLM_PATCH_TARGET, return_value=fake):
        result = parser.parse_and_create(UID, "remind me to call mom tomorrow at 3pm")

    assert result.text == "Call mom"
    assert result.due_at is not None
    assert result.due_at.hour == 15
    assert result.status == CommitmentStatus.OPEN


def test_parses_response_with_null_due_at(parser: CommitmentParserService) -> None:
    """LLM returns due_at=null when no time is implied."""
    fake = json.dumps({"text": "Clean my room", "due_at": None})
    with patch(LLM_PATCH_TARGET, return_value=fake):
        result = parser.parse_and_create(UID, "I should clean my room")

    assert result.text == "Clean my room"
    assert result.due_at is None


def test_parses_response_with_missing_due_at(parser: CommitmentParserService) -> None:
    """LLM omitting due_at entirely is treated as null."""
    fake = json.dumps({"text": "No date here"})
    with patch(LLM_PATCH_TARGET, return_value=fake):
        result = parser.parse_and_create(UID, "just text")

    assert result.due_at is None


def test_parses_response_with_reminder_phrase(parser: CommitmentParserService) -> None:
    """Standard happy path: LLM includes a reminder_phrase alongside text/due_at."""
    fake = json.dumps({
        "text": "Call mom",
        "due_at": "2026-05-17T15:00:00",
        "reminder_phrase": "You said you'd call mom at 3pm — calling now?",
    })
    with patch(LLM_PATCH_TARGET, return_value=fake):
        result = parser.parse_and_create(UID, "remind me to call mom tomorrow at 3pm")

    assert result.reminder_phrase == "You said you'd call mom at 3pm — calling now?"


def test_parses_response_with_missing_reminder_phrase(parser: CommitmentParserService) -> None:
    """LLM omitting reminder_phrase entirely is treated as None (lenient, non-fatal)."""
    fake = json.dumps({"text": "Clean my room", "due_at": None})
    with patch(LLM_PATCH_TARGET, return_value=fake):
        result = parser.parse_and_create(UID, "I should clean my room")

    assert result.reminder_phrase is None


def test_drops_invalid_reminder_phrase_gracefully(parser: CommitmentParserService) -> None:
    """A non-string reminder_phrase is dropped; commitment is still created."""
    fake = json.dumps({"text": "Test", "due_at": None, "reminder_phrase": 42})
    with patch(LLM_PATCH_TARGET, return_value=fake):
        result = parser.parse_and_create(UID, "test")

    assert result.text == "Test"
    assert result.reminder_phrase is None


def test_drops_empty_reminder_phrase_gracefully(parser: CommitmentParserService) -> None:
    """A whitespace-only reminder_phrase is dropped, not stored as-is."""
    fake = json.dumps({"text": "Test", "due_at": None, "reminder_phrase": "   "})
    with patch(LLM_PATCH_TARGET, return_value=fake):
        result = parser.parse_and_create(UID, "test")

    assert result.reminder_phrase is None


# ---------------------------------------------------------------------------
# Timezone handling — regression coverage for the "today" resolution bug
# ---------------------------------------------------------------------------


def test_today_is_resolved_in_the_caller_supplied_timezone(
    parser: CommitmentParserService,
) -> None:
    """
    Previously, "today" was computed with a bare datetime.now() — the
    server's clock, ignoring the caller's timezone entirely (there was no
    timezone parameter at all). Pin "now" to 2026-05-16 23:30 UTC, which is
    still May 16 in UTC but already May 17 in Asia/Tokyo (UTC+9), and
    confirm the date lookup table shown to the LLM reflects the user's
    local calendar date, not the server's.
    """
    fixed_utc = real_datetime(2026, 5, 16, 23, 30, tzinfo=dt_timezone.utc)
    fake = json.dumps({"text": "x", "due_at": None})
    captured: dict[str, str] = {}

    def fake_call_llm(system_prompt: str, user_prompt: str, temperature: float) -> str:
        captured["user_prompt"] = user_prompt
        return fake

    with patch("app.services.commitment_parser_service.datetime") as mock_dt:
        mock_dt.now.side_effect = lambda tz=None: (
            fixed_utc.astimezone(tz) if tz is not None else fixed_utc
        )
        with patch(LLM_PATCH_TARGET, side_effect=fake_call_llm):
            parser.parse_and_create(UID, "test", "Asia/Tokyo")

    prompt = captured["user_prompt"]
    assert "2026-05-17" in prompt
    assert "2026-05-16" not in prompt


def test_today_falls_back_to_utc_when_no_timezone_given(
    parser: CommitmentParserService,
) -> None:
    """No timezone supplied (e.g. an older client) falls back to UTC, matching
    resolve_timezone()'s documented default — not an error, not a crash."""
    fixed_utc = real_datetime(2026, 5, 16, 23, 30, tzinfo=dt_timezone.utc)
    fake = json.dumps({"text": "x", "due_at": None})
    captured: dict[str, str] = {}

    def fake_call_llm(system_prompt: str, user_prompt: str, temperature: float) -> str:
        captured["user_prompt"] = user_prompt
        return fake

    with patch("app.services.commitment_parser_service.datetime") as mock_dt:
        mock_dt.now.side_effect = lambda tz=None: (
            fixed_utc.astimezone(tz) if tz is not None else fixed_utc
        )
        with patch(LLM_PATCH_TARGET, side_effect=fake_call_llm):
            parser.parse_and_create(UID, "test", None)

    assert "2026-05-16" in captured["user_prompt"]


def test_trims_whitespace_from_reminder_phrase(parser: CommitmentParserService) -> None:
    """Surrounding whitespace in reminder_phrase is trimmed before storage."""
    fake = json.dumps({"text": "Test", "due_at": None, "reminder_phrase": "  Trim me  "})
    with patch(LLM_PATCH_TARGET, return_value=fake):
        result = parser.parse_and_create(UID, "test")

    assert result.reminder_phrase == "Trim me"


# ---------------------------------------------------------------------------
# Robustness — LLM output quirks
# ---------------------------------------------------------------------------


def test_strips_json_markdown_fence(parser: CommitmentParserService) -> None:
    """Some models wrap JSON in ```json ... ``` despite instructions."""
    fake = '```json\n{"text": "Test", "due_at": null}\n```'
    with patch(LLM_PATCH_TARGET, return_value=fake):
        result = parser.parse_and_create(UID, "test")
    assert result.text == "Test"


def test_strips_generic_markdown_fence(parser: CommitmentParserService) -> None:
    """Markdown fences without a language tag also get stripped."""
    fake = '```\n{"text": "Test", "due_at": null}\n```'
    with patch(LLM_PATCH_TARGET, return_value=fake):
        result = parser.parse_and_create(UID, "test")
    assert result.text == "Test"


def test_drops_invalid_due_at_gracefully(parser: CommitmentParserService) -> None:
    """Invalid due_at strings are dropped; commitment still created."""
    fake = json.dumps({"text": "Test", "due_at": "not a real date"})
    with patch(LLM_PATCH_TARGET, return_value=fake):
        result = parser.parse_and_create(UID, "test")

    assert result.text == "Test"
    assert result.due_at is None  # invalid date silently dropped


def test_trims_whitespace_from_text(parser: CommitmentParserService) -> None:
    """Surrounding whitespace in text is trimmed before storage."""
    fake = json.dumps({"text": "  Trim me  ", "due_at": None})
    with patch(LLM_PATCH_TARGET, return_value=fake):
        result = parser.parse_and_create(UID, "test")
    assert result.text == "Trim me"


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_raises_when_llm_unavailable(parser: CommitmentParserService) -> None:
    """call_llm returning None (all providers failed) raises CommitmentParseError."""
    with patch(LLM_PATCH_TARGET, return_value=None):
        with pytest.raises(CommitmentParseError, match="LLM unavailable"):
            parser.parse_and_create(UID, "test")


def test_raises_on_invalid_json(parser: CommitmentParserService) -> None:
    """Non-JSON LLM output raises CommitmentParseError."""
    with patch(LLM_PATCH_TARGET, return_value="this is not JSON"):
        with pytest.raises(CommitmentParseError, match="not valid JSON"):
            parser.parse_and_create(UID, "test")


def test_raises_when_text_field_missing(parser: CommitmentParserService) -> None:
    """LLM output missing the 'text' field raises CommitmentParseError."""
    fake = json.dumps({"due_at": "2026-05-17T15:00:00"})
    with patch(LLM_PATCH_TARGET, return_value=fake):
        with pytest.raises(CommitmentParseError, match="missing 'text'"):
            parser.parse_and_create(UID, "test")


def test_raises_when_text_is_empty_string(parser: CommitmentParserService) -> None:
    """Empty text field raises CommitmentParseError."""
    fake = json.dumps({"text": "", "due_at": None})
    with patch(LLM_PATCH_TARGET, return_value=fake):
        with pytest.raises(CommitmentParseError, match="empty"):
            parser.parse_and_create(UID, "test")


def test_raises_when_text_is_whitespace_only(parser: CommitmentParserService) -> None:
    """Whitespace-only text is treated as empty."""
    fake = json.dumps({"text": "   ", "due_at": None})
    with patch(LLM_PATCH_TARGET, return_value=fake):
        with pytest.raises(CommitmentParseError, match="empty"):
            parser.parse_and_create(UID, "test")


def test_raises_when_text_is_not_a_string(parser: CommitmentParserService) -> None:
    """Non-string text (e.g., number) raises CommitmentParseError."""
    fake = json.dumps({"text": 42, "due_at": None})
    with patch(LLM_PATCH_TARGET, return_value=fake):
        with pytest.raises(CommitmentParseError, match="invalid"):
            parser.parse_and_create(UID, "test")
