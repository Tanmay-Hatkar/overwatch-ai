# Engineering Design Document — Overwatch

**Status:** Living document (filled out as architecture decisions are made)
**Last updated:** 2026-05-12

This document captures HOW Overwatch is built — system architecture, data model, layered design, integration patterns, and major engineering decisions.

For the product vision (WHY), see [`PRD.md`](PRD.md).
For individual decisions (WHEN and WHY each choice was made), see [`adr/`](adr/).

---

## 1. System architecture (high level)

_To be filled before slice 1 implementation begins._

Planned shape:

```
React Frontend  ↔  FastAPI Backend  ↔  Database (Postgres / SQLite)
                          ↓
                  External services:
                  - Google Calendar API
                  - LLM providers (OpenAI / Groq / Ollama)
```

## 2. Layered architecture

```
UI (React components)
    ↓ HTTP
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

## 4. API design

_To be filled during slice 1 (Todos), then expanded per slice._

Conventions:
- RESTful endpoints
- Plural resource names (`/todos`, `/commitments`, `/events`)
- Standard HTTP status codes (200/201/204/400/404/409/503)
- JSON request/response bodies via Pydantic models
- Versioning: prefix `/v1/` once the first external user appears (not before)

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

OAuth2 flow. `token.json` stored locally, refreshed automatically. Provider pattern (`CalendarProvider` abstract base) so additional providers (Outlook, Apple) can be added later without touching core logic.

## 7. Deployment

_Not relevant for v1 (local-use only). Will be filled if/when we share with other users._

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
