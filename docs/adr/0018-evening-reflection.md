# 0018: Evening reflection — a cached, LLM-generated look-back on the day

- **Status:** Accepted
- **Date:** 2026-07-09
- **Deciders:** Tanmay Hatkar

## Context

The morning briefing (ADR-0004) looks *forward*: what's on the plate today,
what's overdue, what meetings are coming up. Nothing in the app looks
*back*. At the end of the day the user has no equivalent moment that says
"here's what happened" — they'd have to scroll the commitment list
themselves and mentally tally it up.

This matters for the same reason stale-plan detection (ADR-0017) matters:
Overwatch's job is re-engagement, and re-engagement requires the app to
occasionally initiate a moment of reflection rather than only ever
reacting to what the user opens the app to check. An evening reflection is
the natural end-of-day counterpart to the morning briefing.

The tone constraints are the same non-negotiables that shaped ADR-0017
(from `docs/PRD.md`):
- **"Recall, never judgment."** No percentages, no "only"/"just"/"missed"/
  "failed" — a reflection is not a report card.
- **Agency-preserving.** For anything still open, the reflection must ask
  what to do (carry forward vs. let go), never auto-decide.

## Decision

**Reuse ADR-0004's exact caching pattern (timestamp-based invalidation,
strict `>` freshness check) for a new `reflections` table, and write a
new evening-specific prompt with hard tone rules enforced via worked
good/bad examples.**

### Schema (migration 010)

```sql
CREATE TABLE reflections (
    id              TEXT PRIMARY KEY,
    user_id         TEXT,
    date            TEXT NOT NULL,
    content         TEXT NOT NULL,
    done_count      INTEGER NOT NULL,
    open_count      INTEGER NOT NULL,
    abandoned_count INTEGER NOT NULL,
    generated_at    TEXT NOT NULL,
    UNIQUE(user_id, date)
);
```

Structurally identical to `briefings` (post migration-004's multi-tenancy
rework), plus `abandoned_count` — the reflection looks at three outcomes
(done / still open / abandoned) where the briefing only ever looks at two
(today / overdue).

### Caching — identical mechanism to the briefing (ADR-0004)

```python
def get_today(self, user_id, force_regenerate=False) -> ReflectionResponse:
    today = ...
    if not force_regenerate:
        cached = self._repo.get_for_date(user_id, today)
        if cached is not None and self._is_cache_fresh(user_id, cached):
            return cached
    return self._generate_and_save(user_id, today)

def _is_cache_fresh(self, user_id, cached) -> bool:
    latest = self._service.latest_commitment_update(user_id)
    if latest is None:
        return True
    return cached.generated_at > latest  # strict >, same reasoning as ADR-0004
```

No new reasoning was needed here — ADR-0004 already worked out why strict
`>` (not `>=`) is required (microsecond collision risk) and why
timestamp-based invalidation beats a TTL or explicit cache-busting hooks.
That reasoning applies unchanged to reflections; see ADR-0004 for the full
argument instead of repeating it here.

**One deliberate departure from ADR-0004's literal pattern:** the
reflection's "what day is it" (`today = date.today()` in the briefing)
uses `datetime.now(UTC).date()` here instead of the local server date.
The reflection buckets commitments by `updated_at`, which
`CommitmentRepository` always stamps in UTC — bucketing against a
server-local "today" would silently drift whenever the deploy's system
timezone isn't UTC (verified by a real test failure during
implementation, the same way ADR-0004 caught its own strict-`>` bug). The
briefing doesn't have this issue because it only ever compares `due_at`
(whatever timezone the caller supplied) against its own `today`,
consistently.

### Bucketing (computed in Python, no new repository queries)

`ReflectionService._bucket_commitments()` walks
`CommitmentService.list(user_id)` (all statuses, not just open) and
partitions into:

- **done_today** — `status=done`, `updated_at` is today.
- **still_open** — `status=open` (today's and overdue items both count;
  the reflection doesn't need the briefing's today/overdue split, just
  "what's still hanging").
- **abandoned_today** — `status=abandoned`, `updated_at` is today.

**Recurring roll-forward heuristic:** completing a recurring commitment
rolls it forward to its next occurrence and reopens it instead of closing
it (ADR-0015) — so it never actually reaches `status=done` in storage. We
approximate "completed today" for these by also counting any row where
`recurrence != none AND updated_at is today AND due_at is now in the
future` as done-today. This is a heuristic, not a ledger of individual
completions — it's the same known gap ADR-0015 already accepts (no
audit trail of each individual recurring completion, only the latest
roll-forward state). Documented inline in
`reflection_service.py`'s module docstring and
`_is_recurring_rollforward_today()`.

### Prompt (`app/prompts/evening_reflection.py`)

Same technique as `morning_briefing.py`: an explicit rules list plus a
worked good/bad example pair embedded directly in the system prompt,
because tone rules alone (without a concrete counterexample) are easy for
an LLM to drift from under a slightly different phrasing of the data.

```
Good: "You closed out two of today's plans — the report and the call with
the plumber. 'Update docs' is still open; want to carry it to tomorrow, or
is it done and just not checked off?"

Bad (same input): "You only completed 2 out of 3 tasks today (67%). Try to
finish your remaining tasks tomorrow." — uses 'only', reports a
percentage, and doesn't offer a real choice.
```

The prompt explicitly bans "only," "just" (as a minimizer), "missed,"
"failed," and any percentage/score framing, and requires open items to be
phrased as a question with a real two-way choice (carry forward vs. let
go) rather than a status report.

### Route, service, repository — mirror the briefing stack exactly

`GET /reflections/today[?force_regenerate=true]` mirrors
`GET /briefings/today` field-for-field: same auth dependency
(`current_user`), same 503-on-`ReflectionGenerationError` error handling,
same per-request dependency chain
(`route -> service -> commitment_service + reflection_repo`).

## Alternatives considered

### No caching — regenerate on every request

Simplest option; the reflection is small enough that LLM cost is trivial.

**Rejected:** ADR-0004 already established the concrete downsides (latency
on every load, inconsistent UX from temperature > 0 regenerating slightly
different text on refresh) for the structurally identical briefing case.
No new argument for skipping caching here; consistency with the existing
pattern is itself valuable (one mental model for "cached LLM content keyed
by day" across the app).

### Time-gated ("only show after 6pm")

Only surface the reflection card once real-world evening arrives.

**Rejected for v1:** requires knowing the user's local time zone at the
UI layer and deciding a cutoff, which adds a real design question (what
counts as "evening"? what if they check in at 11pm vs. 4pm?) without a
clear product answer yet. Simpler v1: always show it alongside the
briefing, exactly as instructed by the task — the user decides when to
look at it. A time-gated version is easy to add later purely in the
frontend without touching the backend contract.

### Push notification when the reflection is ready

Proactively notify the user each evening the way `StaleCheckScheduler`
(ADR-0017) proactively asks about dormant plans.

**Rejected for v1:** the reflection is inherently pull ("let me see how
today went"), not push — there's no dormant-plan-style urgency to
justify interrupting the user. Revisit if usage data shows people forget
to check it.

## Consequences

### Positive

- **Zero new caching logic to design or debug** — full reuse of ADR-0004's
  already-battle-tested mechanism (including its lesson about strict `>`).
- **Consistent LLM cost/latency profile** with the briefing: one
  generation per user per day, near-instant on cache hits.
- **Tone enforcement via worked examples**, the same technique that's
  already proven itself in `morning_briefing.py` and `chat.py`.
- **No new repository queries** — bucketing reuses
  `CommitmentService.list()`, keeping the repository's query surface
  unchanged.

### Negative

- **The recurring roll-forward heuristic can misfire.** A recurring item
  completed AND then immediately re-completed (edge case: marking the
  next occurrence done same-day) would double-count as done-today. Same
  class of gap ADR-0015 already accepts; not fixed here.
- **UTC-vs-local "today" departure from the briefing's convention** is a
  subtle inconsistency between the two services' mental models, even
  though it's the more correct choice for this specific bucketing logic.
  Worth revisiting if/when the briefing is ever made timezone-aware too
  (it currently isn't either — see ADR-0004, still local-server-date).
- **No time-of-day gating** means the "evening" reflection can be
  generated and read at 9am, before the day has really happened — the
  content will just be sparse/empty, which the prompt handles gracefully,
  but the framing ("evening reflection") is a bit odd at that hour.

### Future considerations

- Time-of-day gating in the frontend (show after a configurable local
  hour).
- A weekly/monthly rollup view built on the persisted `reflections` table
  (same "history for free" opportunity ADR-0004 noted for briefings).
- Push notification when the reflection is ready, once there's a clearer
  case for it being proactive rather than pull.
- Making the recurring-completion heuristic exact by adding a completion
  ledger (would also close ADR-0015's gap, benefiting both features).

## References

- ADR-0004 — briefing caching strategy (the mechanism reused here
  verbatim; strict `>` reasoning not repeated in this ADR)
- ADR-0015 — recurring commitments via roll-forward (the source of the
  done-today heuristic's known imprecision)
- ADR-0017 — stale-plan detection (the evening reflection's "look back"
  counterpart to that feature's proactive "look at what's gone quiet")
- `docs/PRD.md` — "recall, never judgment," agency
- `backend/app/services/reflection_service.py`
- `backend/app/prompts/evening_reflection.py`
- `backend/migrations/010_reflections.sql`
