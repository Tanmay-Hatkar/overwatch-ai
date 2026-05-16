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
        result = parser.parse_and_create("remind me to call mom tomorrow at 3pm")

    assert result.text == "Call mom"
    assert result.due_at is not None
    assert result.due_at.hour == 15
    assert result.status == CommitmentStatus.OPEN


def test_parses_response_with_null_due_at(parser: CommitmentParserService) -> None:
    """LLM returns due_at=null when no time is implied."""
    fake = json.dumps({"text": "Clean my room", "due_at": None})
    with patch(LLM_PATCH_TARGET, return_value=fake):
        result = parser.parse_and_create("I should clean my room")

    assert result.text == "Clean my room"
    assert result.due_at is None


def test_parses_response_with_missing_due_at(parser: CommitmentParserService) -> None:
    """LLM omitting due_at entirely is treated as null."""
    fake = json.dumps({"text": "No date here"})
    with patch(LLM_PATCH_TARGET, return_value=fake):
        result = parser.parse_and_create("just text")

    assert result.due_at is None


# ---------------------------------------------------------------------------
# Robustness — LLM output quirks
# ---------------------------------------------------------------------------


def test_strips_json_markdown_fence(parser: CommitmentParserService) -> None:
    """Some models wrap JSON in ```json ... ``` despite instructions."""
    fake = '```json\n{"text": "Test", "due_at": null}\n```'
    with patch(LLM_PATCH_TARGET, return_value=fake):
        result = parser.parse_and_create("test")
    assert result.text == "Test"


def test_strips_generic_markdown_fence(parser: CommitmentParserService) -> None:
    """Markdown fences without a language tag also get stripped."""
    fake = '```\n{"text": "Test", "due_at": null}\n```'
    with patch(LLM_PATCH_TARGET, return_value=fake):
        result = parser.parse_and_create("test")
    assert result.text == "Test"


def test_drops_invalid_due_at_gracefully(parser: CommitmentParserService) -> None:
    """Invalid due_at strings are dropped; commitment still created."""
    fake = json.dumps({"text": "Test", "due_at": "not a real date"})
    with patch(LLM_PATCH_TARGET, return_value=fake):
        result = parser.parse_and_create("test")

    assert result.text == "Test"
    assert result.due_at is None  # invalid date silently dropped


def test_trims_whitespace_from_text(parser: CommitmentParserService) -> None:
    """Surrounding whitespace in text is trimmed before storage."""
    fake = json.dumps({"text": "  Trim me  ", "due_at": None})
    with patch(LLM_PATCH_TARGET, return_value=fake):
        result = parser.parse_and_create("test")
    assert result.text == "Trim me"


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_raises_when_llm_unavailable(parser: CommitmentParserService) -> None:
    """call_llm returning None (all providers failed) raises CommitmentParseError."""
    with patch(LLM_PATCH_TARGET, return_value=None):
        with pytest.raises(CommitmentParseError, match="LLM unavailable"):
            parser.parse_and_create("test")


def test_raises_on_invalid_json(parser: CommitmentParserService) -> None:
    """Non-JSON LLM output raises CommitmentParseError."""
    with patch(LLM_PATCH_TARGET, return_value="this is not JSON"):
        with pytest.raises(CommitmentParseError, match="not valid JSON"):
            parser.parse_and_create("test")


def test_raises_when_text_field_missing(parser: CommitmentParserService) -> None:
    """LLM output missing the 'text' field raises CommitmentParseError."""
    fake = json.dumps({"due_at": "2026-05-17T15:00:00"})
    with patch(LLM_PATCH_TARGET, return_value=fake):
        with pytest.raises(CommitmentParseError, match="missing 'text'"):
            parser.parse_and_create("test")


def test_raises_when_text_is_empty_string(parser: CommitmentParserService) -> None:
    """Empty text field raises CommitmentParseError."""
    fake = json.dumps({"text": "", "due_at": None})
    with patch(LLM_PATCH_TARGET, return_value=fake):
        with pytest.raises(CommitmentParseError, match="empty"):
            parser.parse_and_create("test")


def test_raises_when_text_is_whitespace_only(parser: CommitmentParserService) -> None:
    """Whitespace-only text is treated as empty."""
    fake = json.dumps({"text": "   ", "due_at": None})
    with patch(LLM_PATCH_TARGET, return_value=fake):
        with pytest.raises(CommitmentParseError, match="empty"):
            parser.parse_and_create("test")


def test_raises_when_text_is_not_a_string(parser: CommitmentParserService) -> None:
    """Non-string text (e.g., number) raises CommitmentParseError."""
    fake = json.dumps({"text": 42, "due_at": None})
    with patch(LLM_PATCH_TARGET, return_value=fake):
        with pytest.raises(CommitmentParseError, match="invalid"):
            parser.parse_and_create("test")
