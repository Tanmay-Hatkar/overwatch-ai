# Overwatch — Handbook

**Read this first.** This is the one-page map of the project: what Overwatch is, how it's built, and where to look for anything.

If you've never opened this repo before, spend 5 minutes here, then follow the reading order in §2.

---

## 1. What Overwatch is, in one paragraph

A conversational AI that captures the commitments you make to yourself in natural language and surgically reminds you of them — so your plans don't die from neglect. It's not a to-do app. It's not a calendar. It's a **memory layer over your stated commitments.** You say "I'll start prep at 2:30." It writes that down, remembers, and tells you at 2:30. That's the novel mechanic.

The system has three core surfaces:

1. **Chat** — type "remind me to call mom at 7" or "what's overdue?" — the LLM classifies intent, takes action, and replies.
2. **Briefings** — every morning, the LLM looks at today's commitments + calendar events and writes you a one-line "here's your day."
3. **Web Push reminders** — when something hits its due time, your phone or laptop pings — even if the browser tab is closed.

---

## 2. Reading order (do this once)

If you read in this order, you'll have the full mental model in about 2 hours.

| # | File | Time | Why |
|---|---|---|---|
| 1 | This file | 10 min | Bird's-eye view, what to read next |
| 2 | [`README.md`](../README.md) | 5 min | Project pitch, tech stack |
| 3 | [`docs/PRD.md`](PRD.md) | 15 min | What we're building and why |
| 4 | [`CLAUDE.md`](../CLAUDE.md) | 5 min | The 8 non-negotiable code rules |
| 5 | [`docs/adr/0001`](adr/0001-vertical-slicing-and-oop-where-helpful.md) → [`0008`](adr/0008-conversational-chat-interface.md) | 45 min | Every major decision + why we rejected the alternatives |
| 6 | Any service file's docstrings (e.g. [`chat_service.py`](../backend/app/services/chat_service.py)) | 30 min | How the code actually works |
| 7 | [`CONTRIBUTING.md`](../CONTRIBUTING.md) | 5 min | How we ship changes |

After that, you're not just "familiar" — you can confidently add a feature.

---

## 3. Bird's-eye view

```
                            ┌──────────────────────────────┐
                            │      User on phone/laptop     │
                            └──────────────┬───────────────┘
                                           │
                                  Browser / installed PWA
                                           │
       ┌───────────────────────────────────▼────────────────────────────────────┐
       │                          Frontend (React + Vite)                       │
       │                                                                        │
       │   App.jsx ─┬─ BriefingCard ─ StatsBar ─ WeeklyCalendar                  │
       │            ├─ CommitmentList ─ CommitmentForm                           │
       │            ├─ ChatBar  (the conversational surface)                     │
       │            ├─ PushSetup ─ NotificationStatus                            │
       │            └─ SettingsPanel                                             │
       │                                                                        │
       │   sw.js  (Service Worker — push events even when tab is closed)        │
       └───────────────────────────────────┬────────────────────────────────────┘
                                           │
                              HTTP/JSON  (REST endpoints)
                                           │
       ┌───────────────────────────────────▼────────────────────────────────────┐
       │                       Backend (FastAPI, Python 3.12)                   │
       │                                                                        │
       │   Routes layer    →  /chat /commitments /briefings /stats              │
       │   (app/routes/)      /calendar /push /health                           │
       │                                                                        │
       │   Services layer  →  ChatService    BriefingService    PushService     │
       │   (app/services/)    CommitmentService  CalendarService  StatsService  │
       │                      CommitmentParserService  ReminderScheduler        │
       │                                                                        │
       │   Repositories   →  CommitmentRepository    BriefingRepository         │
       │   (app/repos/)      PushSubscriptionRepository                         │
       │                                                                        │
       │   Providers      →  GoogleCalendarProvider     MockCalendarProvider    │
       │   (app/providers/)                                                     │
       │                                                                        │
       │   Agents         →  call_llm()  (single point that hits any LLM)       │
       │   (app/agents/)                                                        │
       └────────┬──────────────────────┬───────────────────────┬────────────────┘
                │                      │                       │
        SQLite (data/overwatch.db)  Ollama/Groq/OpenAI    Google Calendar API
                                    (LLM fallback chain)   + Gmail (read-only)
```

**The rule:** A layer only talks to the layer directly below it. Routes never touch repositories; they go through services. Services never call LLMs or Google directly; they go through agents/providers.

---

## 4. One request, end-to-end

A walk-through of what happens when you type **"remind me to call mom at 7"** into the ChatBar.

### Step 1 — Browser
[`ChatBar.jsx`](../frontend/src/components/ChatBar.jsx) packages your message + last 10 turns of history and POSTs to `/chat`.

### Step 2 — Route
[`routes/chat.py`](../backend/app/routes/chat.py) receives the request, validates the body with the Pydantic `ChatRequest` model, and hands it to `ChatService.handle()`.

### Step 3 — Service
[`services/chat_service.py`](../backend/app/services/chat_service.py) builds a prompt:

- Pulls today's open + overdue commitments from `CommitmentService` (so the LLM is grounded in your real state)
- Pulls today's calendar events from `CalendarService` (auto-routes to GoogleCalendarProvider if `token.json` exists, else `MockCalendarProvider`)
- Injects the conversation history
- Appends today's date + a date lookup table (so "tonight at 7" resolves correctly)

### Step 4 — LLM
The service calls `agents/orchestrator.call_llm()`. This is the **only** place in the codebase that touches an LLM. It tries:

1. **OpenAI** (gpt-4o-mini) — paid, best quality
2. **Groq** (llama-3.1-8b-instant) — free tier, fast
3. **Ollama** (llama3.2) — local, free, no network

If 1 returns an HTTP error or rate limit, it transparently retries with 2. ADR-0002 covers why.

The LLM returns a single JSON object:

```json
{
  "intent": "add_commitment",
  "text": "Call mom",
  "due_at": "2026-06-03T19:00:00",
  "reply": "Got it — I'll remind you to call mom at 7pm tonight."
}
```

### Step 5 — Action
Because `intent === "add_commitment"`, the service calls `CommitmentService.create_commitment(text, due_at)`. That:

- Generates a UUID
- Validates the due_at is a real ISO 8601 datetime
- Calls `CommitmentRepository.insert(...)`

### Step 6 — Database
[`repositories/commitment_repository.py`](../backend/app/repositories/commitment_repository.py) executes a parameterized `INSERT` into the `commitments` table in SQLite.

### Step 7 — Response
The service returns a `ChatResponse(reply, intent, commitment)` to the route. FastAPI serializes it to JSON. The browser receives:

```json
{
  "reply": "Got it — I'll remind you to call mom at 7pm tonight.",
  "intent": "add_commitment",
  "commitment": { "id": "...", "text": "Call mom", "due_at": "2026-06-03T19:00:00", ... }
}
```

### Step 8 — UI update
ChatBar appends both turns to history (persists to `localStorage`), fires `onAction()` which the parent `App.jsx` listens to and refreshes the commitments list / calendar / briefing. A toast pops up: *"Added: Call mom."*

### Step 9 — Later, at 7pm
The **ReminderScheduler** (a background asyncio task started in [`main.py`](../backend/app/main.py) lifespan) ticks every 60 seconds. It queries for commitments whose `due_at` just passed and aren't already notified. For each, it calls `PushService.broadcast(...)` which signs a payload with the VAPID private key and POSTs it to every stored push endpoint.

The browser's service worker ([`sw.js`](../frontend/public/sw.js)) receives the push event — **even if the tab is closed** — and shows a system notification. Click it → focuses the Overwatch tab.

That's one request, end to end.

---

## 5. Slices shipped (status)

Every slice is one vertical feature, end to end (UI + API + DB + tests). Every slice has an ADR.

| # | Slice | Status | Key files | ADR |
|---|---|---|---|---|
| 1 | Commitment CRUD | ✅ Shipped | `commitment_service.py`, `routes/commitments.py` | 0001 |
| 2 | LLM fallback chain | ✅ Shipped | `agents/orchestrator.py` | 0002 |
| 3 | Natural-language commitment parser | ✅ Shipped | `commitment_parser_service.py`, `prompts/commitment_parser.py` | 0003 |
| 4 | Reminder scheduling (polling) | ✅ Shipped | `services/reminder_scheduler.py` | 0004 |
| 5 | Morning briefing + cache | ✅ Shipped | `briefing_service.py`, `prompts/morning_briefing.py` | 0005 |
| 6 | Stats (completion counts, streak, 7-day series) | ✅ Shipped | `stats_service.py`, `routes/stats.py` | — |
| 7a | Calendar provider abstraction | ✅ Shipped | `providers/calendar_provider.py`, `mock_calendar_provider.py` | 0006 |
| 7b | Google Calendar real provider | ✅ Shipped | `providers/google_calendar_provider.py` | 0006 |
| 8 | Web Push notifications (VAPID, SW push event) | ✅ Shipped | `push_service.py`, `routes/push.py`, `sw.js` | 0007 |
| 9 | Weekly calendar UI + briefing card | ✅ Shipped | `BriefingCard.jsx`, `WeeklyCalendar.jsx` | — |
| 10 | Conversational chat (single LLM intent + reply) | ✅ Shipped | `chat_service.py`, `prompts/chat.py`, `ChatBar.jsx` | 0008 |
| 11 | Production-readiness + deploy | 🔨 In progress | (this is what we're working on now) | — |
| 12 | Voice input (Web Speech API) | ⏳ Planned | — | — |

---

## 6. Quick start

### Backend

```bash
cd backend
python -m venv .venv && .venv\Scripts\activate         # Windows
pip install -e ".[dev]"
cp .env.example .env                                    # then fill in keys
python -m uvicorn app.main:app --reload --port 8000
```

Hit `http://localhost:8000/health` — should return `{"status":"ok"}`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Vite's proxy forwards `/commitments`, `/chat`, etc. to the backend on `:8000` — same-origin from the browser's perspective, so no CORS friction during dev.

### Tests

```bash
# Backend
cd backend && pytest

# Frontend (Vitest installed, no tests written yet)
cd frontend && npx vitest
```

---

## 7. How to add a new feature

Follow the vertical-slice playbook (ADR-0001 is the canonical version):

1. **Decide it's worth doing.** Does it serve the PRD? If unclear, write an ADR draft first.
2. **Model.** Add a Pydantic model in `app/models/` if there's a new entity.
3. **Repository** (if it touches the DB). Add to `app/repositories/`. Mirror the existing pattern (constructor takes a connection; one class per table).
4. **Service.** Add to `app/services/`. This is where business logic lives. Constructor takes the repository.
5. **Route.** Add to `app/routes/`. Thin — just validates input, calls service, returns response. Wire it up in `app/main.py`.
6. **Tests.** Unit tests for the service (mock the repo). Integration tests for the route (use the `client` fixture from `conftest.py`).
7. **Frontend.** Add the component under `frontend/src/components/`. Add an API helper to `src/api.js`. Wire into `App.jsx`.
8. **ADR.** If the decision involved a non-obvious trade-off, write one. Use [`docs/adr/template.md`](adr/template.md).

### Where to look when…

| Task | Start here |
|---|---|
| Add a new LLM-touching feature | [`agents/orchestrator.py`](../backend/app/agents/orchestrator.py) + a new prompt in [`prompts/`](../backend/app/prompts/) |
| Add a new background job | [`scheduler/jobs.py`](../backend/app/services/reminder_scheduler.py) pattern + wire in `main.py` lifespan |
| Add a new external integration | New `providers/X_provider.py` implementing the existing abstract base |
| Change how a commitment is stored | [`models/commitment.py`](../backend/app/models/commitment.py) + `commitment_repository.py` + migration in `init_db()` |
| Add a new chat intent | [`prompts/chat.py`](../backend/app/prompts/chat.py) + intent handler in `chat_service.py` |
| Send a different kind of notification | [`push_service.py`](../backend/app/services/push_service.py) — `PushPayload` is the shape |
| Add a new frontend page/route | Currently single-page. Add a new component, conditionally render in `App.jsx`. Add React Router only when there's a real second page. |

---

## 8. The 8 non-negotiable code rules

From [`CLAUDE.md`](../CLAUDE.md), enforced on every commit:

1. **Type hints** on every function param and return.
2. **Docstring** on every function (Args/Returns/Raises).
3. **try/except** on all external calls (Google, Ollama, SQLite, file I/O).
4. **logging** only — never `print()`.
5. **Unit test** for every function; mock all external APIs.
6. **Single responsibility** — one function = one thing; >20 lines = split.
7. **No hardcoded values** — everything in `config.py`.
8. **Secrets in `.env`** only, never committed.

If you're tempted to skip one, write an ADR explaining why instead.

---

## 9. Glossary

- **Commitment** — A thing the user said they'd do. Has `text`, `due_at`, `status` (open/done/snoozed). The primary entity.
- **Briefing** — A morning summary generated by the LLM, cached for the day.
- **Intent** — The LLM-classified category of a chat message: `add_commitment`, `query`, or `general`.
- **Vertical slice** — One end-to-end feature (UI + API + DB + tests). Methodology from ADR-0001.
- **ADR** — Architectural Decision Record. One file per major decision. Always lists alternatives considered.
- **VAPID** — Voluntary Application Server Identification. The crypto keypair that authenticates push payloads to the user's browser push service.
- **Service Worker** — A JS script that runs in the background, independent of any browser tab. The only way to receive Web Push events when the tab is closed.
- **Provider** — An adapter for an external service (calendar, LLM). Lives behind an abstract base so the rest of the code is agnostic.

---

## 10. Where this lives in your head

If you remember one thing from this handbook:

> **Overwatch is a layered Python backend + React frontend, where every external dependency (LLM, calendar, push) lives behind a provider, every feature is shipped as a vertical slice, and every non-obvious decision has an ADR explaining the alternatives we rejected.**

That's the whole shape.
