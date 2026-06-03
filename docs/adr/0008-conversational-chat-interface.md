# 0008: Conversational chat interface with single-LLM intent + reply

- **Status:** Accepted
- **Date:** 2026-06-03
- **Deciders:** Tanmay Hatkar

## Context

After Calendar (slice 7) and Web Push (ADR 0007), the product had every
piece needed for the PRD's "novel mechanic" — capture commitments,
remind surgically — except the actual conversational surface. The
existing UI forces structured form input, even with the Natural Language
toggle (which is still a one-shot parse, not a dialogue).

The user explicitly asked for: *"a working calendar/system where I can
give it my tasks and reminders and it can talk back."* That's a
conversational interface, persistent and multi-turn.

Three things had to be designed together:

1. **The shape of a turn.** Single message → single reply? Or a
   thread with memory? How much context do we keep?
2. **Where intent classification lives.** Frontend? Backend? In the
   LLM call itself? Multiple LLM calls per turn?
3. **What actions chat can take.** All of CRUD? Just create? Read-only
   queries? Side effects on calendar?

## Decision

**A single LLM call per turn that classifies intent AND produces the
reply, with conversation history persisted in localStorage on the
frontend.**

### Shape of a turn

- Frontend POSTs to `/chat` with `{message, history}` where history is
  the last ~10 turns of the conversation (each turn = `{role, content}`)
- Backend returns `{reply, intent, commitment?}` where `commitment` is
  populated only when `intent === 'add_commitment'`
- Frontend appends both the user turn and the assistant turn to its
  history and persists to localStorage
- A 20-turn cap on history prevents unbounded growth; a 10-turn cap
  on the slice sent to the backend prevents runaway token costs

### Intent classification

**One LLM call per turn does both jobs** — classifies the intent AND
generates the natural-language reply, returning a JSON object:

```json
{
  "intent": "add_commitment" | "query" | "general",
  "text": "...",       // only set for add_commitment
  "due_at": "...",     // only set for add_commitment, ISO 8601
  "reply": "..."       // always — the human-facing answer
}
```

Temperature is 0.0 for deterministic JSON. Same `call_llm` orchestrator
fallback chain (OpenAI → Groq → Ollama) — no per-route LLM logic.

### Actions chat can take

For slice 1 of conversational chat:

- **`add_commitment`** — extract text + due_at, create via
  `CommitmentService`, return the new record so the UI can update
- **`query`** — answer using current state. The prompt receives today's
  open commitments, overdue commitments, and today's calendar events
  as context. The LLM is instructed never to invent facts not in that
  context.
- **`general`** — small talk, ambiguous input, or anything else. Reply
  warmly without taking action.

Notably **not** in scope yet: editing commitments via chat, deleting
via chat, marking done via chat, scheduling calendar events via chat.
Those each open the door to "did the user really mean to delete?"
confirmation flows. Defer until the conversational surface is proven.

## Alternatives considered

### Two LLM calls per turn (classify, then act)

A more "agentic" pattern: first call classifies, second call (with
intent-specific prompt) executes the action and generates the reply.

**Rejected because:**
- Double the latency per turn (user waits ~2s instead of ~1s)
- Double the token cost
- The classification is simple enough that a single well-prompted call
  reliably does both (proven in the test suite — 13/13 cases)
- Easy to refactor later if a specific intent needs special handling

### Tool / function-calling API (OpenAI tools, Anthropic tool use)

Use the provider's structured tool-use feature instead of prompting
for JSON.

**Rejected because:**
- Provider-specific — would break the fallback chain (Groq's tool
  support is partial; Ollama's varies by model)
- Our prompt-engineered JSON output works across all three providers
- We could add tool-use as a per-provider optimization later without
  breaking the abstraction

### Conversation history stored in a backend table

Persist the full conversation server-side so it survives device
switches.

**Rejected for now because:**
- Adds a schema migration + repository + sync logic for one user's
  benefit
- localStorage works fine for single-device use
- The relevant context for ANY given turn is just the last 5-10 turns;
  long-term history isn't useful to the LLM
- When we eventually need cross-device sync (multi-user, hosted
  backend), we move it then

### Reuse the existing `/commitments/parse` endpoint for add_commitment

Could chat just call the existing parser for add_commitment intents?

**Rejected because:**
- The parser returns only the structured commitment, not a natural reply
- Two LLM calls per add_commitment turn (route to chat, route to parser)
- Code paths diverge — chat needs reply generation anyway, so do both
  in one call
- The chat prompt is a SUPERSET of the parser prompt (with reply
  generation added); the parser remains useful for non-conversational
  callers (e.g., the existing Natural Language form mode)

## Consequences

### Positive

- **PRD novel mechanic shipped.** The product now matches the elevator
  pitch — a conversational AI that captures commitments and talks back.
- **Single LLM call per turn.** ~1s latency, ~$0.0002 per turn at
  gpt-4o-mini pricing. Trivial cost even at heavy use.
- **Same fallback chain.** OpenAI rate-limited or down → Groq picks up
  transparently. No new resilience work.
- **History decoupled.** localStorage means zero backend state for
  conversation; resync across reloads works for free.
- **Context-aware queries.** Because the prompt receives today's open
  commitments + overdue + calendar events, the LLM can answer
  "what's overdue?" or "what's on my plate?" from grounded data.
- **No new entities.** Chat reuses Commitment + Calendar + their
  services. No `Conversation` table, no migration.

### Negative

- **Single point of failure per turn.** If the one LLM call returns
  malformed JSON or fails, the user gets a 503. Mitigated by markdown
  fence stripping + Pydantic validation + graceful frontend error
  rendering.
- **No conversation across devices.** A user who opens Overwatch on
  their phone won't see chat history from their laptop. Acceptable for
  single-user MVP.
- **History doesn't bound forever.** localStorage has a few-MB quota
  and 20 turns × ~200 chars each = ~4KB. Not a practical worry.
- **`query` intent is read-only.** "Mark X done" via chat doesn't work
  yet. Users still need the checkbox in the list. Could be added in
  a follow-up slice (`update_commitment`, `delete_commitment` intents).
- **Conversational latency competes with the form's instant feel.**
  Form submit is ~300ms; chat submit is ~1s. We don't replace the
  form — both coexist. Power users will use the form for speed; chat
  is for natural-language interaction.

### Future considerations

- Add `update_commitment` / `delete_commitment` / `mark_done` intents
  with a confirmation flow ("Marking 'review PR' as done — confirm?")
- Voice input via Web Speech API on the chat input (continuous mode,
  silence-buffered finalization — mirrors what v1 had)
- Cross-device conversation history via a `conversation_turns` table
  (only when we have hosted multi-user infrastructure)
- Streaming responses (`event: stream` SSE) so the assistant starts
  speaking before the full reply is computed
- "Smart" silent retries on JSON parse failure (one retry with a
  stricter format reminder before failing the turn)

## References

- ADR-0002 — LLM provider fallback chain (still used)
- ADR-0003 — Prompt engineering for structured output (same patterns:
  date lookup table, temperature=0, few-shot examples, defensive
  JSON parsing)
- `backend/app/prompts/chat.py` — system + user templates
- `backend/app/services/chat_service.py` — intent routing + action
- `backend/app/routes/chat.py` — the `/chat` endpoint
- `frontend/src/components/ChatBar.jsx` — the UI
- `backend/tests/unit/test_chat_service.py` — 13 tests covering all
  three intents + history injection + error paths
