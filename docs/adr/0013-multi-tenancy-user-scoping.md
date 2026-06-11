# 0013: Multi-tenancy via row-level user_id scoping

- **Status:** Accepted
- **Date:** 2026-06-11
- **Deciders:** Tanmay Hatkar

## Context

The app shipped with authentication (ADR-0009) and per-user Google Calendar
tokens (ADR-0011), but **everything else was global**. `commitments`,
`briefings`, `push_subscriptions`, and `stats` had no `user_id` — every
signed-in account shared one pool of data. Concretely:

- Any second user would see the first user's todos, briefing, and stats.
- The chat LLM was grounded in the *global* commitment pool, so its
  "context" wasn't really anyone's — a likely cause of it feeling "off."
- A user could receive push reminders for another user's commitments.

This is a correctness, privacy, and product-quality problem. It is also the
precondition for "per-user memory": you can't give a user their own context
until the data is separated by user in the first place. (There is no
"separate LLM per user" — the LLM is stateless; isolation lives in the data,
assembled into the prompt per request.)

## Decision

**Scope every user-owned table by a `user_id` column, and thread `user_id`
through every repository, service, and route.** Authentication already
identifies the user via the `current_user` dependency; we now pass
`user.id` down each call chain so all reads filter by it and all writes
stamp it.

### Schema (migration 004)
- Add `user_id TEXT` to `commitments` and `push_subscriptions` (+ indexes).
- Rebuild `briefings` with `UNIQUE(user_id, date)` (was `UNIQUE(date)`) so
  two users can each have a briefing for the same day.
- **Backfill:** when exactly one user exists (the developer's own account on
  the live deploy), assign all pre-existing rows to that user, so nothing is
  orphaned. Fresh deploys (zero users) are a no-op. With 2+ users we can't
  guess ownership, so rows stay NULL — and since every query filters by
  user_id, NULL-owned rows are simply invisible rather than leaking.

### Code
- Repositories: every method takes `user_id` first; reads `WHERE user_id = ?`,
  writes include it. There is no "all users" read path — that boundary is the
  safety net against cross-tenant leaks.
- Services: thread `user_id` through.
- Routes: every protected route resolves `current_user` and passes `user.id`.
- Chat: the LLM context is now built from the *signed-in user's* commitments
  only.
- ReminderScheduler: iterates `UserRepository.list_all_ids()`, scoping
  commitments and subscriptions per user, so each person's reminders go only
  to their own devices.

### Nullable user_id (for now)
`user_id` is left nullable: SQLite can't add a NOT NULL column to an existing
table without a full rebuild, and the app sets it on every write anyway. The
eventual Postgres migration can tighten it to NOT NULL + a real FK.

## Alternatives considered

### Separate database (or schema) per user
True physical isolation — one DB per tenant.

**Rejected:** massive operational overhead (N databases, N migrations,
connection routing) for a single-user-plus-friends app. Row-level scoping is
the standard approach until you have compliance reasons or very large
tenants.

### Postgres Row-Level Security (RLS) policies
Let the database enforce per-user filtering automatically.

**Rejected (for now):** we're on SQLite, which has no RLS. Enforcing the
filter in the repository layer is explicit, testable, and portable. We can
add RLS as defense-in-depth if/when we move to Postgres.

### A separate LLM/model per user (the intuitive-but-wrong option)
"Give each user their own LLM so it holds their context."

**Rejected — it's a misconception:** LLMs are stateless and hold no context
between calls; a dedicated model wouldn't "remember" anything either.
Per-user context is achieved by assembling that user's data into the prompt
per request — which is exactly what this slice enables. One shared model,
isolated context via user-scoped data.

## Consequences

### Positive
- **Real data isolation.** Each user sees only their own commitments,
  briefings, stats, and reminders. Privacy risk eliminated.
- **Coherent AI.** The chat is grounded in the user's own data — the
  foundation for trustworthy, per-user context and (next) per-user
  conversation memory.
- **Correct reminders.** Each user's push goes only to their devices.
- **Forward-compatible.** The `google_calendar_tokens` table (ADR-0011) was
  already keyed by user_id; everything now matches.
- **Tested.** 210 backend tests green, including new scope tests asserting
  one user can't see another's data.

### Negative
- **Nullable user_id** is a temporary looseness; tightened at the Postgres
  migration.
- **In-memory backfill heuristic** ("exactly one user → assign all") is a
  one-time convenience for the existing single-user deploy; it does nothing
  (correctly) once multiple users exist.
- **Conversation memory still client-side.** This slice scopes *stored* data;
  chat history is still localStorage (per device). Server-side per-user
  conversation memory is the next slice — now unblocked by this one.
- **Briefings still don't include the user's calendar events** (ADR-0011's
  noted gap); unchanged here.

## References
- ADR-0009 — authentication (provides `current_user`)
- ADR-0011 — per-user Google Calendar tokens (the first user-scoped table)
- `backend/migrations/004_user_scoping.sql`
- Every `app/repositories/*`, `app/services/*`, `app/routes/*` touched in
  this slice
- `backend/tests/conftest.py` — `test_user` + `authed_client` fixtures
