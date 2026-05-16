# 0003: Prompt engineering for structured output (date lookup table, temperature, mocked testing)

- **Status:** Accepted
- **Date:** 2026-05-16
- **Deciders:** Tanmay Hatkar

## Context

Slice 3's natural-language commitment parser needs the LLM to convert free-form text like "remind me to call mom tomorrow at 3pm" into a structured JSON object:

```json
{"text": "Call mom", "due_at": "2026-05-17T15:00:00"}
```

Several real challenges make this harder than it sounds:

1. **LLMs are bad at calendar math.** In Overwatch v1, prompts asking the model to compute "what date is tomorrow?" failed regularly. The model would return wrong dates, putting events on the wrong day. This was the single biggest accuracy problem.

2. **LLM output is unreliable.** Even with explicit "return JSON only" instructions, models often:
   - Wrap JSON in markdown code fences (```` ```json ... ``` ````)
   - Add explanatory text before or after the JSON
   - Use slightly wrong JSON syntax (single quotes, trailing commas)
   - Return numbers as strings or vice versa

3. **Tests can't make real LLM calls.** Real API calls in tests would be slow (~500ms each), cost money over time, and would fail when the provider has an outage. Tests must be hermetic.

4. **Temperature affects determinism.** A temperature of 0.7 (the default for creative tasks) produces varied outputs each call. For structured parsing where the right answer is deterministic, we want exact reproducibility.

These together pushed us to adopt several specific prompt-engineering and testing techniques.

## Decision

**Four specific techniques, layered together to produce reliable parsing.**

### 1. Date lookup table injected into every prompt

The user prompt includes a precomputed table of dates the LLM might need:

```
Date lookup (copy dates from this table — do NOT calculate):
  2026-05-16 — Friday (today)
  2026-05-17 — Saturday (tomorrow)
  2026-05-18 — Sunday
  2026-05-19 — Monday
  2026-05-20 — Tuesday
  ...
  (14 days total)
```

The system prompt explicitly tells the model: "COPY exact dates from the lookup table in the user message. Do NOT compute dates yourself."

This eliminates date math from the LLM's responsibility entirely. The model only has to identify *which* row of the table the user means.

### 2. Temperature = 0 for structured output, 0.7 for creative tasks

Two temperatures, one for each use case:

- `LLM_INTENT_TEMPERATURE=0.0` for parsing, classification, anything where the right answer is deterministic
- `LLM_TEMPERATURE=0.7` for briefings, summaries, free-form replies — where varied phrasing is desirable

The parser explicitly passes `temperature=settings.llm_intent_temperature` to `call_llm()`. Without this, identical inputs would sometimes produce slightly different outputs, making the system feel flaky.

### 3. Few-shot examples in the system prompt

The system prompt includes three concrete input/output examples:

```
User: "remind me to call mom tomorrow at 3pm" (today is Friday 2026-05-16, lookup has Saturday=2026-05-17)
Output: {"text": "Call mom", "due_at": "2026-05-17T15:00:00"}

User: "I should finally clean my room"
Output: {"text": "Clean my room", "due_at": null}

User: "submit the Vosyn report by Friday EOD" (today is Mon 2026-05-12, lookup has Friday=2026-05-16)
Output: {"text": "Submit the Vosyn report", "due_at": "2026-05-16T17:00:00"}
```

These cover the three main shapes: explicit time, no time, "end of day" sentinel. The model learns the pattern from examples rather than purely from rules.

This is called **few-shot prompting** — providing examples in-context. It's reliably more effective than zero-shot for structured output.

### 4. Defensive parsing in the service layer

Even with the above, the LLM can produce unexpected output. The parser service handles:

- **Markdown fences:** stripped before JSON parsing (`split("```")` heuristics)
- **Missing `due_at`:** treated as null (not an error)
- **Invalid `due_at` strings:** silently dropped, commitment still created
- **Empty/whitespace `text`:** raises `CommitmentParseError` (HTTP 503)
- **Non-string `text`:** raises `CommitmentParseError`

Philosophy: be **strict on `text`** (the user's commitment is meaningless without it), **lenient on `due_at`** (a wrong date is worse than no date).

### 5. Test by patching at the consumer side

Tests never call the real LLM. They patch `call_llm` where the parser imports it:

```python
# In test_commitment_parser_service.py
LLM_PATCH_TARGET = "app.services.commitment_parser_service.call_llm"

def test_drops_invalid_due_at_gracefully(parser):
    fake = json.dumps({"text": "Test", "due_at": "not a real date"})
    with patch(LLM_PATCH_TARGET, return_value=fake):
        result = parser.parse_and_create("test")
    assert result.due_at is None
```

The patch target is `app.services.commitment_parser_service.call_llm` (where the parser uses it), NOT `app.agents.orchestrator.call_llm` (where it's defined). This is because `from X import Y` copies the reference into the consumer's namespace.

## Alternatives considered

### Let the LLM compute dates from "today is X"

This was v1's approach: tell the model today's date, let it figure out "tomorrow" or "next Tuesday."

**Rejected because:** v1 had real bugs from this. The model would put a "Wednesday" event on Monday because it miscounted days. Removing date math from the LLM eliminates an entire class of errors.

### Use OpenAI's structured output API (response_format=json_schema)

OpenAI's API supports `response_format: {"type": "json_schema", ...}` to guarantee output matches an exact schema. Anthropic has tool-use for similar guarantees.

**Rejected (for now) because:**
- Provider-specific — would break our fallback chain (Groq's free tier only partially supports it; Ollama doesn't)
- Locks us to a single provider for this feature
- The prompt engineering approach is portable across all providers
- We can add structured-output mode later as a per-provider optimization

### Constrained generation / grammar-based decoding

Some inference libraries (llama.cpp, vLLM) support forcing output to match a grammar. The model literally can't produce invalid JSON.

**Rejected because:**
- Not supported by hosted cloud providers (OpenAI, Groq)
- Requires self-hosting, which adds infrastructure complexity
- Our defensive parsing handles the edge cases adequately

### Use higher temperature for variety in `text`

Argument: maybe the LLM produces nicer/varied phrasings at temperature 0.5+.

**Rejected because:** the parsing task is deterministic. The user said "X" and the system should always extract "X" the same way. Variety is a *bug* here, not a feature.

### Test with real LLM calls (record/replay)

Use a library like `vcrpy` to record real LLM responses and replay them in tests.

**Rejected because:**
- Recordings drift from real behavior over time (LLMs improve, change versions)
- First record requires real API credits
- Mocking is simpler and tests exactly the scenarios we care about
- We can add real-LLM integration tests later as a separate test suite if useful

## Consequences

### Positive

- **Dates are always correct.** The biggest v1 bug class is eliminated by design.
- **Output is deterministic.** Same input → same output, every time. Easy to debug, easy to test.
- **Portable across providers.** No provider-specific features means the parser works equally well on OpenAI, Groq, Ollama, Anthropic, Gemini, etc.
- **Tests are hermetic, fast, free.** 14 parser tests run in milliseconds with zero API calls.
- **Error surfaces are explicit.** Missing text → 503. Invalid date → silently dropped. Each failure mode has a clear path.

### Negative

- **Longer prompts.** The date table adds ~150 tokens per request. At gpt-4o-mini pricing, ~$0.000023 per call. Negligible.
- **14-day lookup horizon.** "In 30 days" won't parse correctly because the table only covers 14 days. Acceptable for personal use; would need to extend for power users.
- **Few-shot examples can over-bias.** If the user says something very different from the examples, the model might force-fit to one of the example shapes. Mitigated by `temperature=0` + clear rules.
- **Lost provider-specific guarantees.** OpenAI's structured-output mode is more reliable than prompt engineering. We've chosen portability over guaranteed JSON validity. The defensive parser bridges the gap.

### Future considerations

- **Eval framework.** Once we have 50+ real user inputs, build a small eval set (`tests/eval/parser_examples.json`) to measure prompt quality. "Does the new prompt v3.2 do better than v3.1 on these inputs?"
- **Per-provider structured output.** Optional path: when `call_llm` is using OpenAI, also send `response_format=json_schema`. Gives ironclad JSON for that provider while staying portable elsewhere.
- **Prompt versioning.** As the prompt evolves, version it in code (`PROMPT_V1`, `PROMPT_V2`). Today the prompt is in `prompts/commitment_parser.py` — future ADRs can track changes.
- **Tool use / function calling.** For more complex multi-step parsing (chained commitments, edits to existing commitments), switch to tool-use API. Out of scope for slice 3.

## References

- Few-shot prompting paper (Brown et al., 2020): https://arxiv.org/abs/2005.14165
- OpenAI's structured outputs guide: https://platform.openai.com/docs/guides/structured-outputs
- `unittest.mock.patch` docs: https://docs.python.org/3/library/unittest.mock.html
- The prompt: `backend/app/prompts/commitment_parser.py`
- The parser service: `backend/app/services/commitment_parser_service.py`
- The tests: `backend/tests/unit/test_commitment_parser_service.py`
- ADR-0002: LLM provider fallback chain — sister decision, same slice
