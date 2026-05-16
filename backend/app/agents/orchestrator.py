"""
orchestrator.py — LLM caller with provider fallback chain.

The fallback order is OpenAI -> Groq -> Ollama. Each provider is tried in
sequence; the first that's configured and succeeds returns the reply.
If all fail, returns None.

The rest of the codebase never imports OpenAI/Groq/Ollama directly —
everything goes through call_llm(). Adding a new provider means:
  1. Write a _call_<provider>(...) function with the same signature
  2. Add it to the _PROVIDERS list below
No other code changes.

This is the Strategy + Chain of Responsibility patterns in practice.
"""

import logging

import requests

from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Provider implementations
# Each takes (system_prompt, user_prompt, temperature) and returns the reply.
# Each raises on failure (HTTP error, timeout, malformed response).
# ---------------------------------------------------------------------------


def _call_openai(system_prompt: str, user_prompt: str, temperature: float) -> str:
    """Call OpenAI chat completions API."""
    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": settings.openai_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": settings.llm_max_tokens,
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()


def _call_groq(system_prompt: str, user_prompt: str, temperature: float) -> str:
    """Call Groq API. Same request/response shape as OpenAI."""
    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {settings.groq_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": settings.groq_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": settings.llm_max_tokens,
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()


def _call_ollama(system_prompt: str, user_prompt: str, temperature: float) -> str:
    """Call local Ollama instance. Different response shape than OpenAI."""
    response = requests.post(
        f"{settings.ollama_base_url}/api/chat",
        json={
            "model": settings.ollama_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": settings.llm_max_tokens,
            },
        },
        timeout=60,  # Ollama is slower than cloud providers
    )
    response.raise_for_status()
    return response.json()["message"]["content"].strip()


# ---------------------------------------------------------------------------
# Provider registry — order defines fallback priority
# ---------------------------------------------------------------------------

_PROVIDERS = [
    {"name": "OpenAI", "fn": _call_openai, "enabled": lambda: bool(settings.openai_api_key)},
    {"name": "Groq", "fn": _call_groq, "enabled": lambda: bool(settings.groq_api_key)},
    {"name": "Ollama", "fn": _call_ollama, "enabled": lambda: True},  # always tried as last resort
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def call_llm(
    system_prompt: str,
    user_prompt: str,
    temperature: float | None = None,
) -> str | None:
    """
    Call an LLM via the provider fallback chain.

    Tries providers in order (OpenAI -> Groq -> Ollama). Skips providers
    that aren't configured. Catches and logs each failure before moving
    to the next.

    Args:
        system_prompt: System role message (persona, rules, output format).
        user_prompt: User role message (the actual question or task).
        temperature: Sampling temperature. Pass 0.0 for deterministic
            structured output (JSON parsing, classification). Defaults to
            settings.llm_temperature (0.7) for creative tasks.

    Returns:
        The first successful LLM reply (stripped), or None if every
        configured provider failed.
    """
    if temperature is None:
        temperature = settings.llm_temperature

    for provider in _PROVIDERS:
        if not provider["enabled"]():
            logger.debug(f"LLM provider {provider['name']} skipped (not configured)")
            continue
        try:
            reply = provider["fn"](system_prompt, user_prompt, temperature)
            logger.info(f"LLM reply from {provider['name']} ({len(reply)} chars)")
            return reply
        except Exception as e:
            logger.warning(f"LLM provider {provider['name']} failed: {e}")
            continue

    logger.error("All LLM providers failed (none configured or all errored)")
    return None
