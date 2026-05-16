# 0002: LLM provider fallback chain (OpenAI → Groq → Ollama)

- **Status:** Accepted
- **Date:** 2026-05-16
- **Deciders:** Tanmay Hatkar

## Context

Slice 3 introduces the first LLM-powered feature: natural-language commitment parsing. The backend needs to call an LLM from one or more providers. Several real risks affect this layer:

- **Rate limits:** every provider has them. OpenAI's tier-1 limit is ~500 RPM. A burst of requests can 429.
- **Outages:** providers go down. OpenAI had a multi-hour outage in late 2024. Anthropic in early 2025.
- **Billing issues:** an expired credit card, a depleted balance, or a quota cap kills the feature.
- **Cost differences:** OpenAI gpt-4o-mini is fast and cheap but paid. Groq has a generous free tier with similar capability. Ollama is free but local.
- **Privacy / mode flexibility:** running locally via Ollama keeps sensitive data on-machine. Cloud providers are typically required for accuracy on harder tasks.

Any of those failure modes shouldn't kill the feature for the user. They should fall back gracefully.

This is the same problem traditional backends solve with load balancers and multi-region failover — but at the LLM layer. The pattern is now called "LLM provider routing" or "LLM gateway" in the industry.

## Decision

**Implement a fallback chain across three providers, exposed through a single function.**

The chain order is **OpenAI → Groq → Ollama**, defined in `backend/app/agents/orchestrator.py`:

```python
_PROVIDERS = [
    {"name": "OpenAI", "fn": _call_openai, "enabled": lambda: bool(settings.openai_api_key)},
    {"name": "Groq",   "fn": _call_groq,   "enabled": lambda: bool(settings.groq_api_key)},
    {"name": "Ollama", "fn": _call_ollama,  "enabled": lambda: True},
]

def call_llm(system_prompt, user_prompt, temperature=None) -> str | None:
    for provider in _PROVIDERS:
        if not provider["enabled"]():
            continue
        try:
            return provider["fn"](system_prompt, user_prompt, temperature)
        except Exception as e:
            logger.warning(f"LLM provider {provider['name']} failed: {e}")
    return None
```

Key properties:

- **Single entry point.** The rest of the codebase calls `call_llm(...)` and never imports OpenAI, Groq, or Ollama directly.
- **Configuration via env.** Each provider's API key lives in `.env` (loaded by `pydantic-settings`). An empty key disables that provider — the chain skips it without error.
- **Open for extension, closed for modification.** Adding a new provider (Anthropic, Gemini, etc.) means writing one new `_call_<provider>()` function and adding one entry to `_PROVIDERS`. No changes to `call_llm()`, services, or routes.

This is the **Strategy + Chain of Responsibility** pattern in practice.

### Order rationale

1. **OpenAI first** — best quality at this price point (`gpt-4o-mini` is excellent at structured output, $0.15/$0.60 per 1M tokens). When configured, it's the right default.
2. **Groq second** — fast (Groq custom hardware is ~10x faster than typical inference), generous free tier (~14,400 req/day), OpenAI-compatible API shape. Excellent fallback when OpenAI is unavailable or unaffordable.
3. **Ollama last** — local, free, slow, requires manual setup. Useful as a final safety net and for privacy-sensitive use cases.

## Alternatives considered

### Single provider (OpenAI only)

Just call OpenAI. If it fails, the feature fails.

**Rejected because:** the feature is core to the product. A single point of failure here means the app is broken every time OpenAI is rate-limited or down. The fallback chain costs maybe 30 lines of extra code for substantial resilience.

### Use a managed LLM gateway library (LiteLLM, Portkey)

Libraries like `LiteLLM` already implement multi-provider routing, caching, retries, observability. We could just `pip install` one.

**Rejected because:**
- Overkill for our scale (3 providers, no caching needs yet, no observability stack)
- Adds an external dependency for ~50 lines of native code we can write ourselves
- Limits learning — the point of the fallback chain is to *understand* the pattern, not to abstract it away
- We'd re-introduce the dependency if/when we hit real scale (it's a slice-N decision, not a slice-3 one)

### Abstract base class with concrete provider subclasses

```python
class LLMProvider(ABC):
    @abstractmethod
    def call(self, system_prompt, user_prompt, temperature) -> str: ...

class OpenAIProvider(LLMProvider): ...
class GroqProvider(LLMProvider): ...
```

More "OOP-correct" — use inheritance for the provider interface.

**Rejected because:**
- For 3 providers with the same signature, a list of functions is simpler than a class hierarchy
- Composition (`_PROVIDERS` is a list of dicts with `fn` references) gives us the same polymorphism with less ceremony
- The shared behavior across providers is small (just HTTP POST + JSON parsing); inheritance overhead isn't justified
- Easy to refactor *to* a class hierarchy later if it becomes warranted

### Round-robin / load-balanced multi-provider

Distribute requests across providers (e.g., 70% OpenAI, 30% Groq) for cost/speed optimization.

**Rejected for now because:**
- At our scale (one user, a few requests per day), load balancing is meaningless
- The fallback chain already gives us the resilience benefit
- Load balancing is a slice-N decision when we have actual traffic + cost pressure

## Consequences

### Positive

- **Resilience.** The feature works even when individual providers fail. Tested: when OpenAI returned 401/429 during development, Groq took over transparently.
- **Cost flexibility.** Personal use can run entirely on Groq's free tier ($0/month). Adding $5 OpenAI credit upgrades quality without code changes.
- **Provider independence.** No code in services/routes/UI knows or cares which provider answered. Migrating from OpenAI to Anthropic (or back) is a one-file change.
- **Learning value.** The pattern is interview-relevant: "I built an LLM application with a multi-provider fallback chain" is meaningful in AI/GenAI engineering interviews.
- **Testable.** Tests patch `call_llm` once at the import site (see ADR-0003); the chain itself isn't re-tested per-feature.

### Negative

- **More code to maintain.** Three provider functions instead of one. Each has its own request/response shape (Ollama's API is slightly different from OpenAI's).
- **Marginal cost on failures.** When OpenAI 401s, we waste a few hundred milliseconds before falling back. Not a real cost at our scale, but at high traffic it'd matter.
- **No observability yet.** We log failures but don't track per-provider success rates, latencies, or costs. A real production system would.

### Future considerations

When/if traffic grows:
- Add caching (in front of `call_llm`): semantic + exact-match caching on stable prompts
- Track per-provider latency and cost in `api_usage` table
- Replace ad-hoc fallback with a proper LLM gateway (LiteLLM, Portkey)
- Add rate limiting per user + per provider
- Add retry-with-backoff within each provider before falling through

None of those are needed for slice 3 or any near-term slice. They become real when there are real users.

## References

- LiteLLM (the production-grade version of this pattern): https://github.com/BerriAI/litellm
- Portkey: https://portkey.ai
- OpenAI's rate limits documentation: https://platform.openai.com/docs/guides/rate-limits
- Groq pricing + free tier: https://groq.com/pricing
- The original implementation: `backend/app/agents/orchestrator.py`
- Chain of Responsibility design pattern (Gang of Four)
