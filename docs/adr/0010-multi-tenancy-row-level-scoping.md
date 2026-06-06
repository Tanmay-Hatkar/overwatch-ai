# 0010: Multi-tenancy via row-level user_id scoping

- **Status:** Accepted
- **Date:** 2026-06-04
- **Deciders:** Tanmay Hatkar

## Context

ADR-0009 stood up authentication: we now know *who* is making each
request. But every existing entity — commitments, briefings, push
subscriptions, the cached `token.json` for Google Calendar — is still
implicitly global. Two signed-in users would see each other's data.

For the friends-only launch, that's unacceptable. Each user must see
*only* their own commitments, get *only* their own push notifications,
and authorize *their own* Google Calendar.

This ADR answers three coupled questions:

1. **How do we model tenancy?** Per-row column, per-schema, per-database?
2. **How does it surface in code?** Where do `WHERE user_id = ?` filters live?
3. **How do we migrate existing single-user data?** Tanmay's local DB
   has months of real commitments — losing them is unacceptable.

## Decision

**Row-level multi-tenancy: a `user_id` foreign key on every
user-owned table, enforced at the repository layer.**

### Schema

Migration `003_multi_tenancy.sql` adds:

```sql
ALTER TABLE commitments         ADD COLUMN user_id TEXT;
ALTER TABLE briefings           ADD COLUMN user_id TEXT;
ALTER TABLE push_subscriptions  ADD COLUMN user_id TEXT;
```

Plus a backfill step (described in "Migration plan" below).

After the backfill, `user_id` becomes NOT NULL via a follow-up
migration once we're confident no nulls remain. (SQLite doesn't
support adding NOT NULL constraints to existing columns directly, so
this requires a table rebuild; we defer that to the Postgres migration
in slice 13 where it's a one-liner.)

### A new `google_tokens` table for per-user Calendar OAuth

The single `token.json` file becomes a per-user table:

```sql
CREATE TABLE google_tokens (
    user_id        TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    access_token   TEXT NOT NULL,
    refresh_token  TEXT,
    token_uri      TEXT NOT NULL,
    client_id      TEXT NOT NULL,
    client_secret  TEXT NOT NULL,
    scopes         TEXT NOT NULL,
    expiry         TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);
```

Each user goes through Google's OAuth flow for the Calendar scopes
*after* signing in — separate from the login scopes (ADR-0009).
Their token lives in this table, not on disk.

The existing `token.json` becomes a one-time-import: on first deploy,
if `token.json` exists, the server backfills Tanmay's row.

### Service-layer signature

Every existing service method that touches user-owned data takes a
`user_id` as its first business-logic parameter (after `self`):

```python
# before
def list_commitments(self, status_filter=None) -> list[CommitmentResponse]: ...

# after
def list_commitments(
    self, user_id: UUID, status_filter=None
) -> list[CommitmentResponse]: ...
```

Routes pass it through from the `current_user` dependency:

```python
@router.get("/commitments")
def list_commitments(
    user: UserResponse = Depends(current_user),
    service: CommitmentService = Depends(...),
):
    return service.list_commitments(user.id)
```

### Repository-layer enforcement

Every repository query is scoped by `user_id`. There is no
"unscoped" query path. This is the safety net: even if a service
method forgets to pass user_id, the type system catches it.

```python
def list(self, user_id: UUID, status=None) -> list[CommitmentResponse]:
    rows = self._conn.execute(
        "SELECT * FROM commitments WHERE user_id = ? ...",
        (str(user_id),),
    ).fetchall()
```

### ReminderScheduler becomes per-user

The scheduler currently scans `commitments` as one global pool. After
this change, it iterates over all users and runs the existing check
once per user, sending pushes to that user's subscriptions only.

Cost: one extra query per tick (SELECT id FROM users). At our scale
this is free.

## Alternatives considered

### Schema-per-user (Postgres schemas / SQLite ATTACH DATABASE)

Each user gets their own schema namespace; queries become `SELECT *
FROM "user_xyz".commitments`.

**Rejected because:**
- SQLite doesn't really support this (ATTACH is per-process, requires
  filesystem files per user, has scary limits)
- Even on Postgres, schemas-per-tenant is a 2010s pattern — modern
  multi-tenant apps use row-level scoping
- Cross-tenant analytics (e.g. "how many total users have any
  commitment overdue?") becomes painful
- Adding a column to a table means N schema migrations

### Database-per-user

Each user has their own SQLite file or Postgres database.

**Rejected because:**
- Backup/restore complexity (N files to coordinate)
- Connection pooling becomes per-user (memory pressure)
- Migration coordination across N databases
- The right pattern for true isolation (HIPAA, financial) but
  massive overkill for a friends-only app

### Postgres row-level security (RLS) policies

PostgreSQL has built-in RLS: `CREATE POLICY commitments_user_isolation
ON commitments USING (user_id = current_setting('app.user_id'))`.

**Rejected because:**
- SQLite doesn't have it; we'd lock ourselves out of staying on SQLite
  for local dev
- Requires setting a session-level GUC on every connection — adds a
  per-request side effect that's easy to forget in tests
- Repository-level enforcement is simpler and just as safe in practice
- We can layer RLS *on top* later in Postgres for defense-in-depth,
  but it shouldn't be the only line of defense

### Tenant ID in JWT, trusted by app code without DB filter

Service code reads `user_id` from JWT and passes to the LLM prompt /
push payload, but DB queries don't filter on it.

**Rejected because:**
- Any SQL injection or accidental "fetch all" would expose cross-user
  data
- One mistake in route or service code = data leak
- Defense in depth: the JWT proves identity; the WHERE clause enforces
  isolation. Both layers are cheap

### Use existing `token.json` as a shared calendar for everyone

Keep the single Google account; every user sees Tanmay's calendar.

**Rejected because:**
- Then friends can't sync their own calendars (which is the point)
- Privacy: Tanmay's calendar visible to friends is unacceptable
- The infrastructure for per-user OAuth already exists from ADR-0009;
  it's just a different scope set

## Migration plan

### Migration 003 — add user_id columns (this slice)

1. `ALTER TABLE … ADD COLUMN user_id TEXT` (nullable, no default)
2. Backfill: if exactly ONE user exists (i.e. Tanmay's local case),
   assign all existing rows to that user. If zero or >1 users, leave
   nullable and emit a log warning — only relevant when migrating a
   fresh-install prod DB.
3. Create indexes: `CREATE INDEX idx_commitments_user_id ON
   commitments(user_id)` etc.

The NOT NULL conversion is deferred to a later migration (ideally
post-Postgres-cutover, where `ALTER TABLE … ALTER COLUMN … SET NOT NULL`
is a one-liner).

### `google_tokens` import from `token.json`

A one-shot startup hook: if `token.json` exists AND exactly one user
exists AND that user has no `google_tokens` row, parse the file and
insert it. This handles Tanmay's local migration transparently; new
production environments are unaffected because `token.json` won't
exist.

### Backwards compatibility for stale callers

The `MockCalendarProvider` (used in tests, and when Google is
unconfigured) doesn't need a token, so the new per-user logic
short-circuits when no row is found.

For users who haven't yet authorized Google Calendar, calendar
endpoints return an empty event list with a hint in the response —
no error. This keeps the chat / commitments flow working before the
user opts into calendar sync.

## Consequences

### Positive

- **Real isolation.** A friend signing in only sees their own data,
  enforced at the SQL layer, not just by trusting upper layers.
- **Shareable URL.** Once deployed, sending the link to a friend lets
  them get their own Overwatch with zero risk to other users.
- **Per-user calendars.** Each user authorizes their own Google
  account. No more shared `token.json`.
- **Per-user push.** Reminders go to the right person's devices.
- **Per-user briefings.** The LLM's morning summary is computed from
  this user's commitments, with this user's calendar context.

### Negative

- **Every existing test needs a "current user" fixture.** ~150 tests
  to touch. Most are mechanical (add `user_id=test_user.id` to a few
  calls); a few integration tests need the FastAPI dependency override
  for `current_user`. Counted as part of slice 12's scope.
- **Backfill is fragile.** The single-existing-user heuristic is
  correct for local dev but a fresh production DB has zero users at
  the moment migration 003 runs. We accept this: production starts
  empty, no backfill needed.
- **Calendar provider gets more complex.** Instead of one
  `GoogleCalendarProvider` with a global token, the service now
  needs to construct a provider *per-user*, loading their token from
  the `google_tokens` table on demand. Connection caching across
  requests is a future optimization.
- **ReminderScheduler's "first tick" suppression** (mark already-due
  items as notified without sending) now applies per-user. A new user
  signing in with overdue items shouldn't get a flood — we apply the
  same logic per user, recording first-tick state per user.

### Future considerations

- **Postgres RLS** as defense-in-depth (slice 13+)
- **NOT NULL constraint** on `user_id` columns once we're on Postgres
- **Soft-delete** with cascading (don't immediately drop a user's
  commitments when their account is removed — GDPR-friendly hold
  window)
- **Account deletion endpoint** with full data purge (required for
  any public launch)
- **Audit log** (who-did-what-when) for compliance, not needed for
  friends launch
- **Row-level encryption** at rest for sensitive fields (not needed
  for our commitment text + due dates)

## References

- ADR-0009 — Authentication (this builds directly on `current_user`)
- ADR-0006 — Calendar provider abstraction (the per-user calendar
  token work threads through the existing `CalendarProvider` ABC)
- ADR-0007 — Web Push notifications (the per-user push scheduler
  iterates over `users` instead of the global commitments table)
- ADR-0004 — Reminder scheduler architecture (per-user iteration
  added)
- Migration files in `backend/migrations/` — `003_multi_tenancy.sql`
  and `004_google_tokens.sql`
