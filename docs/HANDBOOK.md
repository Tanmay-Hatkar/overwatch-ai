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
                            │        User on Android        │
                            └──────────────┬───────────────┘
                                           │
       ┌───────────────────────────────────▼────────────────────────────────────┐
       │                 Mobile app (React Native + Expo, mobile/)              │
       │                                                                        │
       │   App.js ─┬─ TodoListScreen   (the Todos — sections derived from due   │
       │           │                    date + optional section tag)            │
       │           ├─ ChatScreen       (the conversational surface: capture,    │
       │           │                    edit, clarify chips, stale check-ins)   │
       │           ├─ BriefingScreen   ReflectionScreen                         │
       │           └─ LoginScreen      (Google sign-in via system browser)      │
       │                                                                        │
       │   On-device: expo-notifications (reminders + stale check-in),          │
       │   modules/ring-alarm (full-screen escalation), modules/widget          │
       └───────────────────────────────────┬────────────────────────────────────┘
                                           │
                     HTTPS/JSON  (REST, Authorization: Bearer <jwt>)
                                           │
       ┌───────────────────────────────────▼────────────────────────────────────┐
       │                       Backend (FastAPI, Python 3.12)                   │
       │                                                                        │
       │   Routes layer    →  /chat /commitments /briefings /reflections        │
       │   (app/routes/)      /calendar /auth /health                           │
       │                                                                        │
       │   Services layer  →  ChatService    BriefingService                    │
       │   (app/services/)    CommitmentService  CalendarService                │
       │                      CommitmentParserService  ReflectionService        │
       │                      StaleCheckScheduler                               │
       │                                                                        │
       │   Repositories   →  CommitmentRepository    BriefingRepository         │
       │   (app/repos/)      ConversationRepository  UserRepository             │
       │                                                                        │
       │   Providers      →  GoogleCalendarProvider     MockCalendarProvider    │
       │   (app/providers/)                                                     │
       │                                                                        │
       │   Agents         →  call_llm()  (single point that hits any LLM)       │
       │   (app/agents/)                                                        │
       └────────┬──────────────────────┬───────────────────────┬────────────────┘
                │                      │                       │
        SQLite (data/overwatch.db)  Ollama/Groq/OpenAI    Google Calendar API
                                    (LLM fallback chain)   (read-only, dormant)
```

The web SPA and its Capacitor wrapper were removed in ADR-0024 (tag
`pre-mobile-only` has them).

**The rule:** A layer only talks to the layer directly below it. Routes never touch repositories; they go through services. Services never call LLMs or Google directly; they go through agents/providers.

---

## 4. One request, end-to-end

A walk-through of what happens when you type **"remind me to call mom at 7"** into the chat.

### Step 1 — App
[`ChatScreen.js`](../mobile/src/screens/ChatScreen.js) sends your message (with the device timezone) through [`api.js`](../mobile/src/api.js), which POSTs to `/chat` with the stored bearer token.

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
The service returns a `ChatResponse(reply, intent, commitment)` to the route. FastAPI serializes it to JSON. The app receives:

```json
{
  "reply": "Got it — I'll remind you to call mom at 7pm tonight.",
  "intent": "add_commitment",
  "commitment": { "id": "...", "text": "Call mom", "due_at": "2026-06-03T19:00:00", ... }
}
```

### Step 8 — UI update
ChatScreen appends both turns and shows the created commitment inline. When you return to the Todos screen it refetches `/commitments`, and [`notifications.js`](../mobile/src/lib/notifications.js) reconciles on-device reminders against the new list.

### Step 9 — Later, at 7pm
Nothing on the server fires. The reminder was scheduled **on the phone** with `expo-notifications`, so it fires even if the app is closed or offline. If you ignore it, [`ringAlarm.js`](../mobile/src/lib/ringAlarm.js) escalates to a full-screen ringing alarm (ADR-0019) via the native `modules/ring-alarm`.

The only server-side background job is the **StaleCheckScheduler**: once ever per commitment, it logs a "still the plan?" assistant turn for plans that have gone quiet (ADR-0017). The app schedules a matching local notification and shows the turn, with reply chips, in chat.

That's one request, end to end.

---

## 5. Slices shipped (status)

Every slice is one vertical feature, end to end (UI + API + DB + tests). Every slice has an ADR.

| # | Slice | Status | Key files | ADR |
|---|---|---|---|---|
| 1 | Commitment CRUD | ✅ Shipped | `commitment_service.py`, `routes/commitments.py` | 0001 |
| 2 | LLM fallback chain | ✅ Shipped | `agents/orchestrator.py` | 0002 |
| 3 | Natural-language commitment parser | ✅ Shipped | `commitment_parser_service.py`, `prompts/commitment_parser.py` | 0003 |
| 4 | Reminder scheduling (polling) | ❌ Replaced | on-device scheduling in `mobile/src/lib/notifications.js` | 0004, 0024 |
| 5 | Morning briefing + cache | ✅ Shipped | `briefing_service.py`, `prompts/morning_briefing.py` | 0005 |
| 6 | Stats (completion counts, streak, 7-day series) | ❌ Built, then removed | contradicted "no streak tyranny" (PRD §5) | 0023 |
| 7a | Calendar provider abstraction | ✅ Shipped | `providers/calendar_provider.py`, `mock_calendar_provider.py` | 0006 |
| 7b | Google Calendar real provider | ✅ Shipped | `providers/google_calendar_provider.py` | 0006 |
| 8 | Web Push notifications (VAPID, SW push event) | ❌ Built, then removed | web client gone; reminders are on-device | 0007, 0024 |
| 9 | Calendar grid UI | ❌ Built, then removed | demoted to Settings-only connect (no UI) | 0022 |
| 10 | Conversational chat (single LLM intent + reply) | ✅ Shipped | `chat_service.py`, `prompts/chat.py`, `ChatScreen.js` | 0008 |
| 11 | Production-readiness + deploy | ✅ Shipped | Railway (backend) | — |
| 12 | Voice input/output (web + native Android) | ⚠️ Removed with the web client; not yet in `mobile/` | was `speech.js`, `nativeTts.js` | 0012, 0016, 0024 |
| 13 | Multi-tenancy / auth | ✅ Shipped, dormant for now | `auth.py`, per-user scoping | 0009, 0013 |
| 14 | Recurring commitments, stale-plan check-in, evening reflection, ring-alarm escalation, home-screen widget | ✅ Shipped | see ADR list | 0015, 0017–0020 |
| 15 | v1 refocus — mobile-first, cut groups/reschedule/stats/dormant forms | ✅ Shipped | this slice | 0022, 0023 |
| 16 | Mobile app (RN/Expo): AI-first capture, ring escalation, widget | ✅ Shipped | `mobile/` | 0019, 0020 |
| 17 | Mobile-only client: remove web SPA, Capacitor, cookie auth, Web Push | ✅ Shipped | — | 0024 |

This table stops tracking new slices in detail as of #15 — for anything
shipped after this, the ADR list in `docs/adr/` is the source of truth,
not this handbook. This doc was last actually walked end-to-end on
2026-07-15; treat older status claims elsewhere in this file (e.g. §4's
JSON examples, which predate recurrence/lead-time/reflections) as
illustrative of the *shape* of the system, not its exact current state.

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

### Mobile

```bash
cd mobile
npm ci
npx expo run:android      # dev build on a device/emulator (needs the Android SDK)
npx expo start --web      # quick browser preview; native modules are stubbed
```

The app talks to `expo.extra.apiBaseUrl` in `mobile/app.json` (production
Railway by default). Point it at `http://<your-LAN-IP>:8000` to use a local
backend.

### Tests

```bash
# Backend
cd backend && pytest

# Mobile (Jest + ESLint, same as CI)
cd mobile && npm test && npm run lint
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
7. **Mobile.** Add a screen under `mobile/src/screens/` or a component under `mobile/src/components/`. Add an API helper to `mobile/src/api.js`. Register screens in `mobile/App.js`.
8. **ADR.** If the decision involved a non-obvious trade-off, write one. Use [`docs/adr/template.md`](adr/template.md).

### Where to look when…

| Task | Start here |
|---|---|
| Add a new LLM-touching feature | [`agents/orchestrator.py`](../backend/app/agents/orchestrator.py) + a new prompt in [`prompts/`](../backend/app/prompts/) |
| Add a new background job | [`stale_check_scheduler.py`](../backend/app/services/stale_check_scheduler.py) pattern + wire in `main.py` lifespan |
| Add a new external integration | New `providers/X_provider.py` implementing the existing abstract base |
| Change how a commitment is stored | [`models/commitment.py`](../backend/app/models/commitment.py) + `commitment_repository.py` + migration in `init_db()` |
| Add a new chat intent | [`prompts/chat.py`](../backend/app/prompts/chat.py) + intent handler in `chat_service.py` |
| Send a different kind of notification | [`mobile/src/lib/notifications.js`](../mobile/src/lib/notifications.js) — on-device, reconciled against the commitment list |
| Add a new screen | New file in `mobile/src/screens/`, register it in the stack in `mobile/App.js` |

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
- **Service Worker** — A JS script that runs in the background, independent of any browser tab. The only way to receive Web Push events when the tab is closed.
- **Provider** — An adapter for an external service (calendar, LLM). Lives behind an abstract base so the rest of the code is agnostic.

---

## 10. Where this lives in your head

If you remember one thing from this handbook:

> **Overwatch is a layered Python backend + React Native mobile app, where every external dependency (LLM, calendar) lives behind a provider, every feature is shipped as a vertical slice, and every non-obvious decision has an ADR explaining the alternatives we rejected.**

That's the whole shape.
