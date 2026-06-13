# 0015: Recurring commitments via roll-forward (not instances)

- **Status:** Accepted
- **Date:** 2026-06-13
- **Deciders:** Tanmay Hatkar

## Context

Real use surfaced a gap: a user said "start my night routine, add it to my
daily routine," and the app could only make a one-off commitment — it had no
concept of *recurrence*. The LLM even understood the request but had nothing
to store it in, so it produced junk (see ADR-0014's discernment fix, which
made it *ask* instead — but the actual capability was still missing).

We needed commitments that repeat (daily/weekly routines). The design
question: how to model a repeating thing?

## Decision

**A `recurrence` field on the commitment ('none' | 'daily' | 'weekly'), with
a "roll-forward on completion" model — not generated instances.**

- A commitment is a single row with a `recurrence`.
- When a recurring commitment is marked **done**, the service does NOT close
  it. Instead it advances `due_at` to the next future occurrence and keeps
  `status = open`. So ticking off tonight's "night routine" makes it reappear
  tomorrow at the same time.
- `_next_occurrence` rolls forward by the period (1 or 7 days) repeatedly
  until the result is in the future — so an overdue routine still lands on its
  next real slot, not a past one.
- The chat LLM extracts recurrence ("every day" → daily, "weekly" → weekly).
- On-device alarms re-sync automatically: when `due_at` rolls forward, the
  client refreshes and schedules the next occurrence's notification.

## Alternatives considered

### Generated instances (a template + many rows)

Store a recurrence "template" and pre-generate/maintain a row per occurrence.

**Rejected (for now):**
- Much heavier: needs a generator, a window of future instances, cleanup of
  old ones, and a way to edit "this one" vs "all".
- Roll-forward gives the core daily-routine UX with **one row** and almost no
  new machinery.
- We can migrate to instances later if we need per-occurrence history.

### A separate "routines" entity distinct from commitments

A parallel concept just for recurring things.

**Rejected:** a routine *is* a commitment that repeats. Splitting them would
duplicate the list UI, the calendar rendering, the chat handling, and the
reminder scheduling. One entity with a `recurrence` field is far simpler.

### A background job that regenerates recurring items

A scheduler that recreates recurring commitments each day.

**Rejected:** roll-forward-on-completion needs no background job — the
advance happens exactly when the user completes the item, which is also the
only moment it matters.

## Consequences

### Positive

- **Routines work end-to-end.** "Night routine daily at 11pm" creates a daily
  commitment; completing it rolls it to tomorrow.
- **Minimal footprint.** One column (migration 006), small service logic, no
  new entity, no background job.
- **Alarms compose for free.** The existing on-device reminder sync picks up
  the rolled-forward `due_at` and schedules the next occurrence.
- **Chat-native.** The LLM sets recurrence from natural language.

### Negative

- **No per-occurrence history.** Because it's one rolling row, we don't keep a
  record of each day it was completed. Acceptable for v1; revisit if streak
  history matters.
- **Roll-forward only triggers on completion.** If a user never marks a
  recurring item done, it just goes overdue (same as any commitment) rather
  than auto-advancing. That's intentional — "you didn't do it" is real signal.
- **Only daily/weekly.** No "every weekday" / custom intervals yet. Easy to
  extend the enum + `_next_occurrence` later.

### Future considerations

- "Every weekday" and custom intervals.
- Per-occurrence completion history (would push toward the instances model).
- Editing recurrence from the list UI (currently set via chat; the badge
  shows it).

## References

- ADR-0014 — chat discernment + clarify (made it *ask* about routines)
- `backend/migrations/006_recurrence.sql`
- `backend/app/models/commitment.py` (Recurrence enum)
- `backend/app/services/commitment_service.py` (roll-forward + `_next_occurrence`)
- `backend/app/prompts/chat.py` (recurrence extraction)
