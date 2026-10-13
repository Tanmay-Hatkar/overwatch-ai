"""
test_orchestrator.py — Unit tests for the LLM fallback chain.

requests.post is mocked; no network. Covers the Groq request body for
reasoning vs. non-reasoning models, and that an empty reply falls through
to the next provider instead of being returned as an answer.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.agents import orchestrator
from app.config import settings


def _ok(content: str) -> MagicMock:
    response = MagicMock()
    response.json.return_value = {"choices": [{"message": {"content": content}}]}
    response.raise_for_status.return_value = None
    return response


@pytest.fixture
def groq_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "openai_api_key", "")
    monkeypatch.setattr(settings, "groq_api_key", "test-key")


@pytest.mark.parametrize(
    ("model", "expected"),
    [("openai/gpt-oss-120b", "low"), ("openai/gpt-oss-20b", "low"), ("llama-3.1-8b-instant", None)],
)
def test_groq_body_sets_reasoning_effort_only_for_reasoning_models(
    monkeypatch: pytest.MonkeyPatch, model: str, expected: str | None
) -> None:
    monkeypatch.setattr(settings, "groq_model", model)
    body = orchestrator._groq_body("sys", "user", 0.0)
    assert body.get("reasoning_effort") == expected
    assert body["model"] == model


def test_groq_body_omits_reasoning_effort_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "groq_model", "openai/gpt-oss-120b")
    monkeypatch.setattr(settings, "groq_reasoning_effort", "")
    assert "reasoning_effort" not in orchestrator._groq_body("sys", "user", 0.0)


def test_call_llm_returns_first_non_empty_reply(groq_only: None) -> None:
    with patch.object(orchestrator.requests, "post", return_value=_ok('  {"ok": true}  ')):
        assert orchestrator.call_llm("sys", "user", 0.0) == '{"ok": true}'


def test_empty_reply_falls_through_to_next_provider(groq_only: None) -> None:
    """Groq answers with '' (reasoning ate the budget); Ollama is tried next."""
    ollama = MagicMock()
    ollama.json.return_value = {"message": {"content": "from ollama"}}
    ollama.raise_for_status.return_value = None
    with patch.object(orchestrator.requests, "post", side_effect=[_ok(""), ollama]) as post:
        assert orchestrator.call_llm("sys", "user", 0.0) == "from ollama"
    assert post.call_count == 2


def test_all_empty_returns_none(groq_only: None) -> None:
    ollama = MagicMock()
    ollama.json.return_value = {"message": {"content": "   "}}
    ollama.raise_for_status.return_value = None
    with patch.object(orchestrator.requests, "post", side_effect=[_ok(""), ollama]):
        assert orchestrator.call_llm("sys", "user", 0.0) is None
