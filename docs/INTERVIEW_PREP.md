# Interview Prep — GenAI Concepts, Explained & Applied in Overwatch

> The study companion for GenAI interviews. For each concept: a
> beginner→pro explanation, then **honestly** how Overwatch uses it (or
> deliberately doesn't), with code pointers, plus an interview-ready way to
> say it. Built from the real architecture — every claim maps to code you
> can open.

**Last updated:** 2026-06-08

---

## How to use this

1. **Be truthful.** For several topics we *chose not to* use the textbook
   approach. Explaining *why you didn't* is a stronger senior answer than
   pretending you did. Each section gives you the honest framing.
2. **Stack note.** Overwatch is **Python / FastAPI / SQLite**. If the role
   is **Java / Spring**, say so up front: *"I built this in Python; these
   GenAI patterns map directly to Spring AI / LangChain4j — the concepts
   are framework-agnostic."*
3. **Open the code while you practice.** Pointers like
   `chat_service.py → handle()` are there so you rehearse against the real
   thing, not a memory of it.

Confidence legend: ✅✅ built thoroughly · ✅ built, can defend · ⚠️ partial
or deliberately skipped — study before claiming.

---

## 1. Tool Calling ✅

### Concept (beginner → pro)
- **Beginner:** Tool calling lets an LLM *do things*, not just talk. You
  describe functions it may call (`create_event(title, time)`); instead of
  prose, the model returns a structured "call this function with these
  args." Your code runs it and feeds the result back.
- **Intermediate:** Providers expose this natively — OpenAI `tools`,
  Anthropic `tool_use`. The model is fine-tuned to emit a JSON tool call
  that conforms to your schema. It's the foundation of agents that act.
- **Pro:** The tradeoffs — native tool calling is **provider-specific**
  (schemas and reliability differ across vendors), adds a round-trip, and
  couples you to one API. The alternative is **prompt-engineered structured
  output**: instruct the model to emit JSON directly. You lose the
  provider's guarantees but gain portability.

### In Overwatch (honest)
We use **prompt-engineered JSON**, not native tool calling. The chat LLM
returns `{"intent": "...", "text": "...", "due_at": "...", "reply": "..."}`
and our code acts on `intent`. Same *idea* (LLM decides an action, code
executes), different *mechanism*.
- Pointers: `prompts/chat.py` (the JSON contract in `SYSTEM_PROMPT`),
  `chat_service.py → handle()` (executes the decided action), ADR-0008.
- **Why:** native tool calling would break our OpenAI→Groq→Ollama fallback
  chain — Groq's tool support is partial, Ollama's varies by model. JSON
  works across all three.

### Say it in the room
> "I implemented LLM-driven actions via prompt-engineered structured JSON
> rather than native tool calling — a deliberate choice to keep a
> multi-provider fallback chain working. I can speak to both, and when I'd
> use native tool use: single-provider apps where its schema guarantees and
> reliability outweigh the portability cost."

---

## 2. AI Agent System Design ✅

### Concept (beginner → pro)
- **Beginner:** An "AI agent" is software that uses an LLM to decide what to
  do. A chatbot that can take actions is a simple agent.
- **Intermediate:** Two flavors. **AI Agent** = the LLM is *one component*;
  deterministic code controls when it runs and what happens with its
  output. **Agentic AI** = the LLM is *in the driver's seat*, looping and
  choosing its own next actions until a goal is met (AutoGPT, LangGraph).
- **Pro:** Design is about *boundaries and reliability*. What does the LLM
  decide vs. what does code decide? How do you bound it (it can't run
  forever or touch the DB directly)? Single-call vs. multi-step loop —
  latency, cost, and predictability tradeoffs. Failure handling when the
  probabilistic component misbehaves.

### In Overwatch (real, strong)
A focused **AI Agent** (not agentic):
- `chat_service.py` — one LLM call classifies intent (`add_commitment` /
  `query` / `general`) **and** drafts the reply.
- `agents/orchestrator.py → call_llm()` — the single chokepoint to any
  LLM; the fallback chain lives here.
- **Boundary:** the LLM *classifies and drafts*; deterministic services
  *execute* (create the commitment, run the SQL query). The LLM never
  touches the database — a clean trust boundary.
- **Tradeoff made:** single call (classify + reply together) over a
  two-call agent loop — half the latency and cost, proven in tests
  (ADR-0008).

### Say it in the room
> "I designed a narrow agent with a strict boundary: the LLM classifies
> intent and drafts language; deterministic services perform all
> side-effects. I chose a single-call design over an agentic loop for
> latency, cost, and reliability — and I know when I'd reach for a
> multi-step agent: open-ended tasks where the steps aren't known up front."

---

## 3. Model Memory & Context Management ✅✅ (your strongest)

### Concept (beginner → pro)
- **Beginner:** LLMs have no memory — they forget everything between calls.
  Any "memory" is something *you* re-supply in the prompt each time.
- **Intermediate:** The **context window** is the token budget per call.
  Memory management = deciding what to include: recent conversation,
  relevant data, instructions — and what to drop when you run out of room.
- **Pro:** Short-term (this conversation) vs. long-term (across sessions)
  memory are different problems. Strategies: sliding windows, summarization
  of old turns, retrieval of only relevant context, token budgeting per
  call. "Context engineering" is increasingly the core craft.

### In Overwatch (built thoroughly)
- **Conversational memory:** `ChatBar.jsx` keeps the last ~20 turns, sends
  the last ~10 to the backend per request (a sliding window to bound token
  cost).
- **Persistence:** localStorage so history survives reloads (ADR-0008
  chose client-side over a backend table for the single-user MVP).
- **Context injection:** every chat prompt (`prompts/chat.py → USER_TEMPLATE`)
  is built with the user's *live* data — today's open commitments, overdue,
  calendar events — so "what's overdue?" is answered from grounded state.
- **Just-in-time context:** a date lookup table + current time/timezone are
  injected so relative dates ("tonight at 7", "tomorrow") resolve
  correctly.
- **Budgeting:** explicit caps — 10 turns, `llm_max_tokens=500` in
  `config.py`.

### Say it in the room
> "Because LLMs are stateless, I engineered memory explicitly: a sliding
> window of conversation history with token-budget caps for short-term
> memory, plus dynamic context injection of the user's live data so
> queries are grounded rather than hallucinated. I also inject current
> time and a date table so relative-time language resolves deterministically."

---

## 4. Model Parameters & Fine-Tuning ✅ (params) / ⚠️ (fine-tuning)

### Concept (beginner → pro)
- **Beginner:** Parameters tweak how the model responds *at runtime*.
  `temperature` is the big one: 0 = deterministic/factual, ~1 =
  creative/varied.
- **Intermediate:** Others — `top_p` (nucleus sampling), `max_tokens`
  (length + cost cap), `frequency/presence_penalty`. You tune these per
  task. **Fine-tuning** is different: you retrain the model's weights on
  your own labeled examples to bake in behavior.
- **Pro:** The decision rule — *exhaust prompting + parameters before
  fine-tuning.* Fine-tuning costs money, slows iteration, needs a quality
  labeled dataset (often thousands of examples), and risks overfitting.
  It wins for high-volume, narrow, *stable* tasks where prompting plateaus.

### In Overwatch (honest)
- **Parameters: yes, deliberately.** `config.py` —
  `llm_intent_temperature=0.0` for structured/JSON extraction (we want
  determinism), `llm_temperature=0.7` for briefings (we want some warmth),
  `llm_max_tokens=500` for cost control.
- **Fine-tuning: no.** We chose prompt engineering — we don't have a large
  labeled dataset, and prompting met the quality bar.

### Say it in the room
> "I tune inference parameters per task — temperature 0 for deterministic
> JSON extraction, 0.7 for generative summaries, and a max-tokens cap for
> cost. I made a deliberate call to use prompt engineering over
> fine-tuning given our data volume, and I understand the threshold where
> fine-tuning pays off: a high-volume, narrow, stable task with labeled data."

> ⚠️ **Study gap:** the *mechanics* of fine-tuning (LoRA/PEFT, dataset
> prep, eval) — you haven't done it hands-on. Skim before the interview so
> you can discuss it confidently.

---

## 5. MCP — Model Context Protocol ⚠️ (not built; study)

### Concept (beginner → pro)
- **Beginner:** MCP is a standard way to plug tools and data into an LLM
  app — "USB-C for AI." Write a connector once; any MCP-compatible client
  can use it.
- **Intermediate:** Open standard from Anthropic. Three primitives —
  **tools** (model-callable functions), **resources** (data the app
  exposes to the model), **prompts** (reusable templates). A *server*
  exposes these; a *client* (Claude Desktop, Claude Code) consumes them.
- **Pro:** It decouples capability from client — your "GitHub MCP server"
  works in any MCP host without bespoke integration. Solves the M×N
  integration explosion (M models × N tools) by standardizing the
  interface.

### In Overwatch (honest)
**Not built.** Our action layer is the custom JSON-intent approach, not
MCP. But there's a true, useful story: *the Claude Code agent used to build
this project runs on MCP*, so you've worked alongside it as a consumer and
understand the primitives.

### Say it in the room
> "I haven't authored an MCP server in this project — our tool layer is
> custom. But I understand MCP's three primitives (tools, resources,
> prompts) and the M×N integration problem it solves, and I've worked with
> MCP-based tooling. I could stand up a server from the official SDK."

> ⚠️ **Study gap (high priority if the role wants it):** do the Anthropic
> "Introduction to MCP" course and build one toy server (~2 hours). Then
> you can speak from real experience, not theory.

---

## 6. RAG Architectures ⚠️ (deliberately skipped; can defend)

### Concept (beginner → pro)
- **Beginner:** RAG = Retrieval-Augmented Generation. Give the LLM
  knowledge it wasn't trained on (your docs) by *retrieving* relevant
  pieces and putting them in the prompt.
- **Intermediate:** Pipeline — (1) chunk documents, (2) embed each chunk
  into a vector, (3) store in a vector DB (pgvector, Pinecone, Weaviate),
  (4) embed the query, (5) retrieve top-k similar chunks, (6) inject into
  the prompt. Grounds answers, cuts hallucination.
- **Pro:** The hard parts — chunking strategy, hybrid search
  (keyword + vector), re-ranking, handling stale data, and *evaluation*
  (is retrieval actually surfacing the right context?). RAG is for
  **unstructured** knowledge.

### In Overwatch (honest, and a strong answer)
**Not used — deliberately.** Our knowledge is **structured** (commitments
in SQL rows), so we retrieve with plain SQL and inject the results into the
prompt. That's "retrieval-augmented" in spirit without embeddings or a
vector store.
- Pointers: `briefing_service.py` / `chat_service.py` pull the user's rows
  and inject them as context.

### Say it in the room
> "I evaluated RAG and chose against it: our knowledge is structured
> relational data, so SQL retrieval plus context injection grounds the
> model without the cost and failure modes of embeddings and a vector
> store. I know RAG is the right tool for unstructured documents, and I can
> design that pipeline — chunking, embeddings, vector store, top-k
> retrieval, re-ranking, and eval."

> ⚠️ **Study gap:** if the JD leans on RAG, build one small demo (pgvector
> + an embedding model + a 10-doc corpus) so you have hands-on to point to.

---

## 7. Cache Memory (Redis, semantic caching) ✅ (app-level) / ⚠️ (Redis/semantic)

### Concept (beginner → pro)
- **Beginner:** LLM calls are slow and cost money, so you cache results to
  avoid repeating work.
- **Intermediate:** Levels — **exact-match** cache (same input → stored
  output, e.g. Redis key/value); **application** caching (cache a *derived*
  result and invalidate it when inputs change); response caching at the API
  layer.
- **Pro:** **Semantic caching** — cache by *meaning*: embed the query, and
  if a new query is sufficiently similar to a cached one, return the cached
  answer ("what's the weather" ≈ "how's the weather"). Tradeoff: a
  similarity threshold that's too loose returns wrong answers. Redis is the
  common backing store; vector-enabled caches do the semantic variant.

### In Overwatch (honest)
**Application-level caching with invalidation** — not Redis, not semantic:
- `briefing_service.py` (ADR-0005): today's briefing is generated once and
  cached; we serve the cache unless a commitment changed since it was
  generated (**timestamp-based invalidation** via
  `latest_commitment_update()`). Saves an LLM call on every page load.
- Stored in SQL, single-process. No Redis, no semantic layer.

### Say it in the room
> "I implemented result caching with timestamp-based invalidation for
> LLM-generated content to eliminate redundant model calls — same goal as a
> Redis cache. I understand the progression: Redis for shared cache across
> instances, and semantic caching (embed the query, similarity-match) for
> near-duplicate prompts, with the similarity-threshold risk that implies."

> ⚠️ **Study gap:** Redis basics + the semantic-cache mechanism. You own
> the *concept* (cache + invalidation); learn the *tools*.

---

## 8. Validation Logic & Guardrails ✅✅

### Concept (beginner → pro)
- **Beginner:** LLMs are probabilistic — they sometimes return malformed
  output, make things up, or wander off-topic. Guardrails keep them safe
  and reliable.
- **Intermediate:** Input validation, **output schema validation**,
  grounding instructions ("only answer from provided context"), scope
  limits, retries on bad output, graceful fallbacks.
- **Pro:** Defense in depth at *every* boundary — validate what goes in,
  constrain what the model may do, validate what comes out, and degrade
  gracefully on failure. Content moderation, PII handling, refusal
  boundaries, and observability of when guardrails fire.

### In Overwatch (built thoroughly)
- **Output validation:** LLM JSON is parsed into **Pydantic models** —
  schema enforced; malformed shapes rejected (`chat_service.py`, the
  `models/` package).
- **Defensive parsing:** `_parse_json()` strips markdown ```json fences the
  model sometimes adds before parsing.
- **Grounding guardrail:** the prompt instructs *"answer only from the
  provided context, never invent facts"* — anti-hallucination
  (`prompts/chat.py`).
- **Scope guardrail:** only 3 intents; anything off-topic routes to a safe
  `general` reply.
- **Lenient-but-safe fields:** an invalid `due_at` is dropped rather than
  failing the whole parse (`commitment_parser_service.py → _extract_due_at`).
- **Failure handling:** `try/except` on every external call; an LLM failure
  becomes a graceful 503, never a crash; the provider fallback chain is
  itself a reliability guardrail.

### Say it in the room
> "I layered guardrails at every boundary: Pydantic schema validation on
> all LLM output, defensive JSON parsing for formatting drift, prompt-level
> grounding to prevent hallucination, scoped intents, lenient field
> handling for partial failures, and graceful degradation with a provider
> fallback chain. I treated the reliability of a probabilistic component as
> a first-class design concern."

---

## The scorecard (memorize this)

| Topic | Status | Confidence |
|---|---|---|
| Tool Calling | JSON over native (can defend the why) | ✅ |
| AI Agent Design | Built a real narrow agent | ✅ |
| Memory & Context | Built thoroughly | ✅✅ |
| Parameters & Fine-Tuning | Params yes; fine-tuning studied | ✅ / ⚠️ |
| MCP | Not built; consumed via Claude Code | ⚠️ |
| RAG | Deliberately skipped; can justify + design | ⚠️ |
| Caching | App-level + invalidation; Redis/semantic studied | ✅ / ⚠️ |
| Validation & Guardrails | Built thoroughly | ✅✅ |

**4 strong from real work, 4 to shore up with ~1–2 days of focused study**
(fine-tuning mechanics · one MCP server · one small RAG demo · Redis +
semantic caching). Then you speak truthfully to all 8.

---

## The 60-second project pitch (when they say "tell me about a GenAI project")

> "I built Overwatch — a conversational AI productivity assistant, deployed
> and in daily use. The core is an LLM agent with a strict boundary: a
> single model call classifies user intent and drafts a reply, while
> deterministic services execute all side-effects, so the LLM never touches
> the database directly. It runs on a provider fallback chain —
> OpenAI → Groq → Ollama — so it stays up if any provider fails. I engineer
> the model's memory explicitly: a sliding window of conversation history
> plus dynamic injection of the user's live data so answers are grounded,
> not hallucinated. Reliability of the probabilistic layer was a first-class
> concern — Pydantic schema validation on every model output, defensive
> JSON parsing, prompt-level grounding, and graceful degradation. I made
> deliberate architecture calls too: prompt-engineered JSON over native tool
> calling to preserve provider portability, and SQL retrieval over RAG
> because the knowledge is structured, not documents. It's all behind a
> layered architecture with an ADR for every non-obvious decision."

---

## Likely follow-ups (practice these)

1. **"Why not just use OpenAI tool calling?"** → portability across the
   fallback chain; Groq/Ollama tool support varies. (Topic 1)
2. **"How do you stop the model from hallucinating?"** → grounding prompt +
   inject only real data + Pydantic validation on output. (Topics 3, 8)
3. **"How do you manage cost?"** → temp 0 determinism, max-tokens cap,
   briefing cache to avoid redundant calls, Groq free tier as primary.
   (Topics 4, 7)
4. **"When would you add RAG here?"** → when knowledge becomes
   unstructured (user uploads notes/docs); then embeddings + vector store +
   retrieval. (Topic 6)
5. **"How would this scale to many users?"** → multi-tenancy (user_id
   scoping), SQLite→Postgres, Redis for shared cache, per-user rate limits.
6. **"Agent vs agentic — which is this and why?"** → AI Agent; chose it
   over an agentic loop for latency/cost/predictability on a task with
   known steps. (Topic 2)

---

## Deeper reading

- The decisions + alternatives, formally: [docs/adr/](adr/) (esp. 0002,
  0003, 0005, 0008)
- The project story: [THE_BUILD_LOG.md](THE_BUILD_LOG.md)
- The architecture map: [HANDBOOK.md](HANDBOOK.md)
- Concept theory to round out the gaps: [LEARNING.md](LEARNING.md) *(if
  created)* — Karpathy, 3Blue1Brown, Anthropic courses, MCP docs
