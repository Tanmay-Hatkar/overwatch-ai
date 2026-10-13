# Engineering Design Document — Overwatch

**Status:** Living document (filled out as architecture decisions are made)
**Last updated:** 2026-10-09

This document captures HOW Overwatch is built — system architecture, data model, layered design, integration patterns, and major engineering decisions.

For the product vision (WHY), see [`PRD.md`](PRD.md).
For individual decisions (WHEN and WHY each choice was made), see [`adr/`](adr/).

---

## 1. System architecture (high level)

```
Mobile app (React Native + Expo)  ↔  FastAPI backend  ↔  SQLite
   on-device: notifications,              ↓
   ring alarm, widget              External services:
                                   - LLM providers (OpenAI / Groq / Ollama)
                                   - Google Calendar API (read-only, dormant)
```

`mobile/` is the only client (ADR-0024). It authenticates with a bearer
JWT obtained via Google sign-in in the system browser, deep-linked back as
`overwatch://auth?token=…`. Due-time reminders and the stale-plan
notification are scheduled **on the device**; the server's only background
job is the StaleCheckScheduler, which records the one-time check-in as a
conversation turn. See `HANDBOOK.md` §3–4 for the component map and a
request walkthrough.

## 2. Layered architecture

```
UI (React Native screens/components, mobile/)
    ↓ HTTPS + Bearer token
Routes (FastAPI functions)
    ↓
Services (business logic classes)
    ↓
Repositories (data access classes)
    ↓
Database
```

**Rules:**
- A layer talks only to the layer directly below.
- No route ever talks to a repository directly — always through a service.
- Each layer is independently testable by mocking the layer below.

## 3. Data model

_To be filled during slice 1._

Primary entity: **Commitment**. Schema to be designed.

Other entities likely:
- `User` (single-user for v1, but the model leaves room)
- `ExternalEvent` (cached Google Calendar events)
- `Reflection` (evening review records)

### Goal (weekly rate goal, ADR-0026)

The PRD §4.4 shape of a commitment: "do X, N times, this week".

- `goals` — `id, user_id, text, target_count, status (active|archived),
  decision (keep_going|call_it_good|NULL), decision_week (Monday, user-local),
  created_at, updated_at`
- `goal_logs` — `id, goal_id, user_id, amount, logged_at (UTC)`

Progress is computed on read, never stored: the sum of `goal_logs.amount`
inside the user's current week, [Monday 00:00, next Monday 00:00) in their
timezone. The API returns it with `done_this_week`, `remaining`,
`days_left` and a `state` of `in_progress | check_in | met | settled`.

`GoalRepository` (SQL only) → `GoalService` (week arithmetic, state) →
`routes/goals.py`. `ChatService` takes an optional `GoalService` for the
`add_goal` / `log_goal` intents.

## 4. API design

_To be filled during slice 1 (Todos), then expanded per slice._

Conventions:
- RESTful endpoints
- Plural resource names (`/todos`, `/commitments`, `/events`)
- Standard HTTP status codes (200/201/204/400/404/409/503)
- JSON request/response bodies via Pydantic models
- Versioning: prefix `/v1/` once the first external user appears (not before)

Goals (ADR-0026), all taking `?timezone=<IANA name>`:

| Method | Path | Purpose |
|---|---|---|
| GET | `/goals` | active goals + this week's progress |
| POST | `/goals` | create `{text, target_count}` |
| PATCH | `/goals/{id}` | rename / re-target / archive |
| DELETE | `/goals/{id}` | delete goal and logs |
| POST | `/goals/{id}/log` | add progress `{amount=1}` |
| DELETE | `/goals/{id}/log` | undo this week's latest log |
| POST | `/goals/{id}/week-decision` | `{decision: keep_going \| call_it_good \| null}` |

## 5. LLM strategy

Provider fallback chain: **OpenAI → Groq → Ollama**

_Details to be filled in slice 4 (first LLM-touching slice)._

Considerations to address there:
- Where prompts live in the codebase
- Token budgets per call type
- Cost tracking / logging
- Privacy boundary (which prompts can leave the machine)

## 6. External integrations

### Google Calendar

_To be filled in slice 2 (first integration slice)._

Read-only, background context only (ADR-0022). The browser-based connect
flow was removed with the web client (ADR-0024); stored per-user tokens and
the providers remain, so a mobile connect flow can plug in later. Provider pattern (`CalendarProvider` abstract base) so additional providers (Outlook, Apple) can be added later without touching core logic.

## 7. Deployment

Backend on Railway with a SQLite volume (see `DEPLOYMENT.md`). The mobile
app is built with Expo (`expo run:android` / EAS) and points at the backend
via `expo.extra.apiBaseUrl` in `mobile/app.json`.

## 8. Logging & observability

_To be filled in slice 1 — conventions established with the first feature._

Likely: structured logging via Python's `logging` module with JSON formatter. Standard fields: timestamp, level, request_id, action, latency_ms.

## 9. Testing strategy

_To be filled in slice 1 — conventions established with the first feature._

Targets:
- ≥80% line coverage on backend
- Unit tests at function / class level (mock all external dependencies)
- Integration tests at route level (use an in-memory SQLite fixture)
- Manual end-to-end verification before marking a slice "done"
