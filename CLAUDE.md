# CLAUDE.md — Working agreement for Claude Code

This file is auto-loaded by Claude Code on every chat. It defines the project context, working agreements, and pointers to detailed docs.

---

## Project goal

Overwatch is a conversational AI productivity assistant that captures the commitments users make in natural language and surgically reminds them at the time they said.

The core problem it solves is **re-engagement** — plans dying from neglect, not from being unmade.

For the full product vision, read [`docs/PRD.md`](docs/PRD.md) before discussing features, scope, or user-facing decisions.

---

## Reference docs — read when relevant

- [`docs/PRD.md`](docs/PRD.md) — product vision, target user, scope.
  **READ** before discussing features, scope changes, or user-facing decisions.

- [`docs/EDD.md`](docs/EDD.md) — engineering design, data model, architecture.
  **READ** before discussing implementation, new classes, or system changes.

- [`docs/adr/*.md`](docs/adr/) — one decision per file.
  **READ** when you need to know WHY a specific choice was made.
  **CREATE** a new ADR when a significant decision is being made (next sequential number).

## When to update these docs

- Scope or product change → update `docs/PRD.md`
- Architecture or data model change → update `docs/EDD.md`
- New significant decision → **create a new ADR** (do NOT edit historical ones — they are historical record)

---

## Working agreement

### Methodology

- **Vertical slicing.** Build one feature end-to-end (DB → API → UI → tests → CI → merged PR) before starting the next. Never build all of one layer first.
- **One step at a time.** Do not push pace. The user sets cadence.
- **Explain before code.** Describe the plan and theory before writing code. The user must agree before implementation.
- **Wait for the user.** Never end a message with "now do X, Y, Z" or anything that pushes them toward action. Lay out options, let them choose.

### Code style

- **OOP where it helps, functions where it doesn't.** Use classes for: stateful logic (repositories, services), polymorphism (LLM providers, calendar providers), domain entities. Use functions for: pure utilities, FastAPI route handlers, Pydantic models.
- **SOLID principles** applied universally regardless of class vs function.
- **Type hints on every function** parameter and return.
- **Docstrings** on every public function (Args / Returns / Raises).
- **try/except on all external calls** (LLM, Google API, database, file I/O).
- **logging only** — no `print()` in committed code.
- **No hardcoded values** — all constants in `config.py` or `.env`.
- **Single Responsibility** — one function = one thing. Functions >20 lines are usually doing too much.

### Architecture (high level)

Layered architecture:

```
Models (Pydantic)            ← data shapes
    ↑
Repositories (classes)       ← data access; encapsulate DB
    ↑
Services (classes)           ← business logic; orchestrate repositories
    ↑
Routes (functions)           ← FastAPI handlers; translate HTTP ↔ service calls
    ↑
UI (React components)        ← display + interaction
```

Each layer depends only on the one below. **No skipping layers.** A route never talks directly to a repository — it goes through a service.

### Definition of Done (per slice)

A slice is "done" when:

- Feature works end-to-end (manually verifiable)
- Unit tests cover new code (target ≥80% line coverage)
- Integration tests cover new API endpoints
- All linters pass (`ruff`, `prettier`)
- ADR written if a non-trivial decision was made
- PR merged to `main` (squash) with CI green
- README / EDD updated if architecture or setup changed

---

## Git conventions

- **Conventional Commits**: `feat:`, `fix:`, `refactor:`, `docs:`, `chore:`, `test:`, `style:`, `perf:`
- **Trunk-based development**: short-lived feature branches off `main`, squash-merged via PR
- **Self-review before merge**: read your own diff
- **Never push directly to `main`.** Always PR — even when solo.
- **Never force-push to `main`.**
- **Never use `--no-verify`** to skip pre-commit hooks. Fix the underlying issue.

Full details in [`CONTRIBUTING.md`](CONTRIBUTING.md).

---

## Tech stack (current)

- **Language:** Python 3.12 (backend), JavaScript/JSX (frontend)
- **Backend:** FastAPI + uvicorn
- **Frontend:** React + Vite + Tailwind CSS
- **Database:** Postgres via Supabase (cloud), SQLite (local dev)
- **LLM providers:** OpenAI (primary), Groq (fallback), Ollama (local fallback)
- **External APIs:** Google Calendar, Gmail (slice 2+)
- **Testing:** pytest + pytest-mock (backend), Vitest (frontend, slice 1+)
- **Linting/formatting:** ruff (Python), prettier (frontend)

Update this section if the stack changes. Create an ADR for any stack-level decision.
