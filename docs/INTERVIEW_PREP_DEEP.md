# Interview Prep — Deep Dive (the techniques we actually built)

> The elaborated companion to [INTERVIEW_PREP.md](INTERVIEW_PREP.md). That
> doc covers all 8 client topics + the scorecard + pitch. **This** one goes
> deep — real code from Overwatch, the concept behind each line, and the
> senior-level "why" — on the techniques we genuinely implemented. The
> not-built topics (RAG, Redis/semantic caching, MCP, fine-tuning) are
> summarized at the end so you can still talk to them, but the depth here
> is on what you can defend from real work.

**Last updated:** 2026-06-08

Everything below maps to actual files. Open them while you read:
`chat_service.py`, `agents/orchestrator.py`, `models/chat.py`,
`prompts/chat.py`, `config.py`, `briefing_service.py`.

---

## 1. Structured Output (our "tool calling")

### The concept, deeper
An LLM normally returns free-form prose. To make it *drive software*, you
need its output in a machine-readable shape. Two routes:

- **Native tool/function calling** — the provider exposes an API where you
  declare function schemas; the model returns a validated call. Reliable,
  but provider-specific.
- **Prompt-engineered structured output** — you *instruct* the model to
  emit JSON matching a schema, then parse + validate it yourself. Portable
  across any provider, at the cost of doing your own validation.

We chose the second. The senior insight: **structured output is the
*general* technique; tool calling is one vendor-specific implementation of
it.** Understanding that distinction is the answer.

### The contract (what the model must return)
From `models/chat.py` — the schema the LLM's output is validated against:

```python
class _ChatIntentResult(BaseModel):
    intent: ChatIntent          # Literal["add_commitment","query","general"]
    text: str | None = None     # extracted commitment title (add_commitment only)
    due_at: str | None = None   # ISO 8601 datetime or null
    reply: str                  # always — the human-facing answer
```

The model is told (in `prompts/chat.py`) to return exactly this JSON. One
call does **two jobs**: classify the intent *and* write the reply.

### Why this is a strong answer
- It's the same capability as tool calling (LLM decides an action, code
  executes) without coupling to one vendor's API.
- It keeps the **provider fallback chain** working (next section) — Groq
  and Ollama have inconsistent native tool support; JSON works everywhere.
- You can articulate exactly when you'd switch: a single-provider app where
  the vendor's tool-call reliability and schema enforcement are worth the
  lock-in.

### Say it
> "I treat structured output as the core technique and native tool calling
> as one vendor-specific flavor of it. I prompt the model to emit a typed
> JSON object — intent plus extracted fields plus reply — then validate it
> against a Pydantic schema. That keeps me provider-agnostic, which matters
> because I run a fallback chain across vendors with different tool-call
> support."

---

## 2. AI Agent System Design + LLM Resilience

### The concept, deeper
An agent's quality is defined by its **boundaries** and its **failure
behavior**, not by how clever the prompt is.

- **Boundary:** what does the LLM decide vs. what does deterministic code
  decide? A good design never lets the probabilistic component do something
  irreversible on its own.
- **Resilience:** LLM providers rate-limit, time out, and go down. A
  production agent must survive that.

### The boundary, in code
`chat_service.py → handle()` is the whole agent loop, and notice how
*little* the LLM is trusted with:

```python
raw = call_llm(SYSTEM_PROMPT, user_prompt, temperature=settings.llm_intent_temperature)
if raw is None:
    raise ChatError("LLM unavailable — no provider succeeded")
result = self._parse_json(raw)               # validate before trusting

commitment = None
if result.intent == "add_commitment":
    commitment = self._create_commitment(result, user_tz)   # CODE does the write
return ChatResponse(reply=result.reply, intent=result.intent, commitment=commitment)
```

The LLM **classifies and drafts**. Deterministic code **executes** — it
parses, validates, converts timezones, and performs the database write.
The model never issues SQL, never touches the DB. That's the trust
boundary you describe in an interview.

### The resilience, in code
`agents/orchestrator.py` is the single chokepoint to *any* LLM, and it's a
textbook **Chain of Responsibility + Strategy** pattern:

```python
_PROVIDERS = [
    {"name": "OpenAI", "fn": _call_openai, "enabled": lambda: bool(settings.openai_api_key)},
    {"name": "Groq",   "fn": _call_groq,   "enabled": lambda: bool(settings.groq_api_key)},
    {"name": "Ollama", "fn": _call_ollama, "enabled": lambda: True},  # local last resort
]

def call_llm(system_prompt, user_prompt, temperature=None):
    for provider in _PROVIDERS:
        if not provider["enabled"]():
            continue
        try:
            return provider["fn"](system_prompt, user_prompt, temperature)
        except Exception as e:
            logger.warning(f"LLM provider {provider['name']} failed: {e}")
            continue
    return None   # every provider failed → caller degrades gracefully
```

Senior points to make:
- **Single point of integration** — the rest of the codebase never imports
  OpenAI/Groq/Ollama. Adding a provider = one function + one list entry.
- **Graceful degradation** — total failure returns `None`, which the
  service turns into a clean 503, never a crash.
- **Cost/latency strategy hides here too** — Groq (free, fast) can be
  primary; OpenAI is fallback; Ollama (local) is the offline safety net.

### Say it
> "I designed a narrow agent with a hard boundary: the LLM classifies
> intent and drafts language; deterministic services do every side-effect,
> so the model never touches the database. For resilience I route all calls
> through one orchestrator implementing a provider fallback chain —
> OpenAI to Groq to Ollama — using Chain-of-Responsibility, so a provider
> outage is transparent and total failure degrades gracefully to a 503."

---

## 3. Memory & Context Management (your strongest)

### The concept, deeper
LLMs are **stateless**. Every call starts from zero. So "memory" is an
engineering artifact: on each request you reconstruct exactly the context
the model needs, within a token budget, and drop the rest. The craft is in
*what* you inject and *how you bound it*.

Overwatch injects four kinds of context, all in
`chat_service.py → _build_user_prompt()`:

### (a) Conversational memory — a sliding window
```python
for turn in request.history[-10:]:        # only the last 10 turns
    speaker = "User" if turn.role == "user" else "Assistant"
    convo_lines.append(f"  {speaker}: {turn.content}")
```
And the schema enforces the bound (`models/chat.py`):
```python
history: list[ChatTurn] = Field(default_factory=list, max_length=20, ...)
```
Client keeps 20, sends 10 — a **sliding window** that caps token cost. This
is the textbook short-term-memory pattern.

### (b) Grounding context — the user's live data
```python
open_items = self._service.list(status=CommitmentStatus.OPEN)
today_open = [c for c in open_items if c.due_at and c.due_at.date() == today_date]
overdue    = [c for c in open_items if c.due_at and c.due_at.date() < today_date]
```
Today's open + overdue commitments + today's calendar events are injected
so a `query` like "what's overdue?" is answered from **real rows**, not the
model's imagination. This is *retrieval-augmented* in spirit (SQL is the
retriever) without embeddings — because the data is structured.

### (c) Temporal context — solving statelessness for time
The model doesn't know the time unless you tell it. We inject the current
local clock and a 14-day date table:
```python
now_time = now_local.strftime("%I:%M %p").lstrip("0")   # "4:42 PM"
for i in range(14):
    d = now_local + timedelta(days=i)
    marker = " (today)" if i == 0 else " (tomorrow)" if i == 1 else ""
    lookup_lines.append(f"  {d.date().isoformat()} — {day_names[d.weekday()]}{marker}")
```
Now "in 30 minutes", "tonight at 7", "next Tuesday" all resolve
deterministically. The **date table** is a deliberate trick: LLMs are bad
at date arithmetic, so we make them *copy* from a table instead of
calculating (ADR-0003).

### (d) Per-user timezone — context that travels across devices
The browser sends its IANA timezone; the server anchors "today" to the
user's wall clock, not the server's:
```python
now_local = datetime.now(self._resolve_timezone(request.timezone))
```
This is the kind of detail that separates "works on my machine" from
"works for a user in Toronto talking to a server in US-West."

### Say it
> "Because LLMs are stateless, I reconstruct context every call within a
> token budget: a sliding window of conversation history, the user's live
> commitments and events injected so queries are grounded in real data, and
> temporal context — current local time plus a date lookup table — so
> relative-time language resolves deterministically. I also pass the user's
> timezone so 'today' is their wall clock, not the server's."

---

## 4. Model Parameters (tuned per task)

### The concept, deeper
`temperature` controls randomness in token sampling. At **0** the model is
near-deterministic — it picks the highest-probability token every time,
ideal when you need a stable, parseable structure. Higher (~0.7) injects
controlled variety — good for natural language that shouldn't sound robotic.
`max_tokens` caps output length, which caps both latency and cost.

### In code — different temperature for different jobs
The chat router needs reliable JSON, so it forces determinism:
```python
raw = call_llm(SYSTEM_PROMPT, user_prompt, temperature=settings.llm_intent_temperature)
# settings.llm_intent_temperature = 0.0
```
The briefing generator wants warmth, so it uses the default creative temp
(`settings.llm_temperature = 0.7`). All three live in `config.py` (rule:
no hardcoded values), and `max_tokens=500` caps every call:
```python
"max_tokens": settings.llm_max_tokens,   # in every provider call
```

### The senior nuance
- **temp 0 for structured extraction** isn't just "be accurate" — it's
  "make the output *stable enough to parse*." A creative temperature would
  occasionally reorder keys or add prose, breaking the JSON parse.
- **One model, two personalities** via parameters alone — no fine-tuning
  needed. That's the build-vs-buy judgment: parameters + prompting covered
  the requirement.

### Say it
> "I tune parameters per task: temperature 0 for the intent classifier so
> the JSON is stable and parseable, 0.7 for generative summaries so they
> read naturally, and a max-tokens cap on every call for cost and latency.
> Same model, two behaviors, no fine-tuning — a deliberate call given our
> data volume."

---

## 5. Validation Logic & Guardrails (defense in depth)

### The concept, deeper
A probabilistic component will eventually return garbage: malformed JSON,
missing fields, hallucinated facts, off-topic output. Production-grade
design puts a guardrail at **every** boundary — input, the model's
freedom, output, and failure — so no single bad generation breaks the app.

### (a) Input validation — at the door
Pydantic enforces bounds before anything runs (`models/chat.py`):
```python
message: str = Field(..., min_length=1, max_length=2000)
history: list[ChatTurn] = Field(..., max_length=20)
timezone: str | None = Field(default=None, max_length=64)
```

### (b) Output validation — never trust raw model text
`chat_service.py → _parse_json()` does two layers:
```python
cleaned = raw.strip()
if cleaned.startswith("```"):                       # 1) strip markdown fences
    cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
    cleaned = cleaned.rsplit("```", 1)[0]
try:
    data = json.loads(cleaned)                      # 2a) must be valid JSON
except json.JSONDecodeError as e:
    raise ChatError(...)
try:
    return _ChatIntentResult(**data)                # 2b) must match schema
except Exception as e:
    raise ChatError("LLM output missing required fields")
```
Models love wrapping JSON in ```json fences despite instructions — so we
defensively strip them, *then* parse, *then* validate against the Pydantic
schema. Three gates before the output is trusted.

### (c) Grounding guardrail — anti-hallucination in the prompt
The system prompt instructs the model to answer `query` intents **only**
from the injected context and never invent facts. Combined with (b)'s
data injection, the model literally has the real rows in front of it.

### (d) Scope guardrail — a bounded action space
Only three intents exist. Anything ambiguous or off-topic routes to
`general` — a safe reply with no side-effect. The model can't invent a new
kind of action.

### (e) Graceful partial failure — don't fail the whole turn
If `add_commitment` comes back without usable text, or with a bad date, we
degrade instead of erroring:
```python
if not text:
    logger.warning("add_commitment intent missing text; skipping create")
    return None
...
except (ValueError, TypeError):
    logger.warning(f"chat: invalid due_at dropped: {result.due_at!r}")  # drop the date, keep the commitment
```

### (f) Failure as a guardrail — the fallback chain + clean 503
`call_llm` returning `None` becomes a `ChatError` → a user-readable 503,
never a stack trace to the user. The provider fallback chain itself is a
reliability guardrail.

### Say it
> "I treated reliability of a probabilistic component as a first-class
> concern with defense in depth: Pydantic input bounds, then defensive
> output handling — strip formatting drift, parse, and schema-validate
> before trusting anything — prompt-level grounding to prevent
> hallucination, a bounded three-intent action space, graceful partial
> failure that drops a bad field rather than the whole turn, and a fallback
> chain that degrades to a clean 503."

---

## 6. Caching with Invalidation (cost + latency control)

### The concept, deeper
LLM calls are the slowest, priciest part of the request. If an output only
changes when its inputs change, **cache the output and invalidate on
input change** — you avoid paying for the model on every page load. This is
*application-level* caching (caching a derived result), distinct from a
Redis key/value cache or a semantic cache.

### In code — timestamp-based invalidation
`briefing_service.py`: today's briefing is generated once, then served from
cache **unless a commitment changed since it was generated**:
```python
def _is_cache_fresh(self, cached) -> bool:
    latest = self._service.latest_commitment_update()   # MAX(updated_at)
    if latest is None:
        return True
    return cached.generated_at > latest                 # stale if data changed after generation
```
The invalidation signal is a timestamp comparison: *was any commitment
touched after this briefing was generated?* If yes, regenerate; if no,
serve the cache (no LLM call). ADR-0005.

### The senior nuance
- It's **content-aware invalidation**, not a blind TTL — the cache is
  exactly as fresh as the underlying data, no staler.
- Honest known limitation (good to mention): it doesn't catch *deletions*
  without a tombstone — a deleted commitment may linger in the cached
  briefing until the next mutation. Knowing your cache's failure modes is a
  senior signal.
- The scaling path: this is single-process SQL caching; the next step for
  multi-instance is Redis as a shared store, and semantic caching for
  near-duplicate prompts.

### Say it
> "I cache LLM-generated content with content-aware invalidation — a
> briefing is regenerated only when its underlying commitments changed,
> detected by a timestamp comparison, not a blind TTL. It eliminates
> redundant model calls. I know its limits — it doesn't catch deletes
> without a tombstone — and the scaling path to Redis and semantic caching."

---

## The not-built topics (talk to them honestly, briefly)

You didn't build these in Overwatch. Don't pretend you did — explain the
concept and the *judgment* around it.

- **RAG** — for *unstructured* knowledge (docs): embed → vector store →
  top-k retrieve → inject. We deliberately use SQL retrieval instead
  because our knowledge is structured. *"Right tool for documents; I'd add
  it the day users upload notes."*
- **MCP** — open standard to expose tools/resources/prompts to any LLM
  client; the Claude Code agent that built this runs on it. *"Understand the
  primitives; haven't authored a server yet."*
- **Redis / semantic caching** — shared cache store / cache-by-meaning. We
  built app-level caching; Redis is the multi-instance evolution.
- **Fine-tuning** — retraining weights on labeled data; we chose
  prompting + parameters. *"Worth it for high-volume, narrow, stable tasks
  with a dataset."*

For each, a focused day of hands-on (one RAG demo, one MCP server, Redis
basics, fine-tuning concepts) turns "I understand it" into "I've done it."

---

## How to rehearse

1. Open each file referenced above and **trace the real flow** while
   reading the section — you want to speak from the code, not this doc.
2. For each of the 6 built topics, practice: **concept → our
   implementation → the senior nuance → "when I'd do it differently."**
   That four-beat structure reads as senior.
3. Pair with [THE_BUILD_LOG.md](THE_BUILD_LOG.md) (Chapter 4: deploy war
   stories, Chapter 5: the forks) for the "hard problem" and "tradeoff"
   behavioral questions.
4. Keep the [INTERVIEW_PREP.md](INTERVIEW_PREP.md) scorecard + 60-second
   pitch handy as the quick-reference layer.
