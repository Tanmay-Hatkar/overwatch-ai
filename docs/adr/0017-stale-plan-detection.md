# 0017: Stale-plan detection — a one-time "still the plan?" check-in

- **Status:** Accepted
- **Date:** 2026-07-09
- **Deciders:** Tanmay Hatkar

## Context

Overwatch's core problem is re-engagement — plans dying from neglect, not
from being unmade (see PRD). Today the app has two ways a commitment gets
attention: the reminder scheduler (fires once a due time passes) and the
morning briefing (surfaces overdue items every day). Neither handles the
case where a commitment has simply gone *quiet* — no due date, or a due
date that's come and gone with no update — and the user hasn't touched it
in days. The overdue item just sits there, silently, forever, or it gets
buried in an ever-growing "overdue" bucket the briefing repeats every
morning.

Repeating the same nudge every day risks exactly what the PRD says this
app must never become: a nagging todo list. But saying nothing forever
is the opposite failure — the plan dies from neglect, invisibly.

The product principles that bound the solution (from `docs/PRD.md`):
- **"Recall, never judgment."** No scorekeeping, no guilt language.
- **Every interaction preserves user agency.** Offer choices, never
  auto-decide or auto-abandon on the user's behalf.
- **"Respectful by default, aggressive only on permission."** A check-in
  about a dormant plan should not become a recurring nag.

## Decision

**A dormant open commitment gets asked about — "Still the plan?" — exactly
ONCE, ever. The ask goes out via push AND a logged conversation turn (so
it's visible without push permission). The user's next chat message is
then interpreted as a reply, updating state (or not) without the user
having to reply in any rigid format.**

### Schema (migration 009)

```sql
ALTER TABLE commitments ADD COLUMN stale_check_sent_at TEXT DEFAULT NULL;
ALTER TABLE commitments ADD COLUMN stale_check_acknowledged_at TEXT DEFAULT NULL;
```

Two nullable timestamps, not a boolean or a separate table:
- `stale_check_sent_at` — when we asked. `NULL` = never asked. This is a
  one-way door: once set, `list_stale_candidates()` never returns the row
  again, so the ask can never repeat.
- `stale_check_acknowledged_at` — when the user's reply was processed.
  `NULL` = pending. `ChatService` intercepts the user's next message while
  this is `NULL` for any commitment.

### Candidate selection

A commitment qualifies for a check-in when ALL of:
- `status = 'open'`
- never asked before (`stale_check_sent_at IS NULL`)
- not touched in `STALE_CHECK_THRESHOLD_HOURS` (default 4h,
  `settings.stale_check_threshold_hours`)
- has no due date, OR its due date is today or earlier — a plan for next
  week isn't stale yet; only ones whose moment has arrived, or has none,
  qualify

### The scheduler (mirrors `ReminderScheduler`'s structure)

`StaleCheckScheduler` polls every `STALE_CHECK_POLL_INTERVAL_SECONDS`
(default 900s). For each user's candidates, it:
1. Sends a push (`tag=f"stale:{commitment.id}"` — a distinct prefix from
   the reminder scheduler's bare `str(commitment.id)`, so the two never
   collide in the browser's notification-replacement semantics).
2. Appends the same message as an assistant turn via
   `ConversationRepository`, so the ask is visible in the chat history
   even if the user never granted push permission.
3. Calls `mark_stale_check_sent()` regardless of push delivery success.
   The guarantee is "we asked," not "they saw it" — push is a
   best-effort delivery channel, not the source of truth.

**Dedup is persisted in the database, not in-memory.** This differs from
`ReminderScheduler`, whose in-memory `_notified_ids` set resets on every
process restart (acceptable there because a reminder can legitimately fire
again if it's still overdue). A stale-plan check-in must never repeat, so
its "have we asked" state has to survive restarts — hence a DB column, not
a set.

**First-tick suppression** (mirrored from `ReminderScheduler`): the very
first tick after this feature deploys could find many pre-existing dormant
commitments simultaneously — anything that predates the migration and
happens to already be quiet. Firing a check-in burst for all of them at
once would be jarring, so the first tick of each process silently marks
current candidates as sent without asking.

**Unlike `ReminderScheduler`, `StaleCheckScheduler` starts unconditionally**
in `main.py`'s lifespan, even when VAPID isn't configured. Its "we asked"
guarantee is fulfilled by the conversation-turn append alone; there's no
push-only reason to skip it the way there is for the reminder scheduler
(which has literally nothing to do without push).

### Reply interception (`ChatService`)

Before its normal add/query/clarify/general pipeline, `ChatService.handle()`
checks `list_pending_stale_checks(user_id)`. If any exist, ONE small
dedicated LLM call (`app/prompts/stale_check_reply.py`,
`_StaleCheckReplyResult`) classifies the user's message into an outcome:

- `still_valid` — no state change; the plan stands.
- `abandon` — commitment marked `abandoned` (never deleted, never framed
  as failure — a choice the user made).
- `reschedule` — `due_at` updated via the existing `_parse_due_at` helper
  (same timezone handling as the normal add_commitment path). If the LLM
  couldn't extract a specific new time, `due_at` is left unchanged rather
  than guessed at.
- `unrelated` — the message doesn't answer the check-in at all. The
  pending check-in(s) are still acknowledged (so they're never
  re-intercepted), but the SAME message then falls through to the normal
  chat pipeline unchanged, so the user isn't forced to answer before doing
  anything else.

When multiple check-ins are pending simultaneously, one reply resolves all
of them — the classifier is fed the full list of pending commitments and
its single outcome is applied uniformly. This is a deliberate v1
simplification: a user replying to a batch of quiet items ("yeah, still
doing all of that") shouldn't have to answer once per item.

If the classifier's LLM call itself is unavailable or returns unparseable
output, the pending check-in(s) are left pending (not acknowledged) and
the message falls through to normal handling — a transient LLM hiccup on
this side-call never blocks or corrupts the user's actual message.

### Roll-forward interaction with recurrence (ADR-0015)

When a recurring commitment rolls forward (completed → next occurrence,
stays open), `CommitmentService.update()`'s roll-forward branch now also
calls `CommitmentRepository.clear_stale_check()`, resetting both
timestamps to `NULL`. A rolled-forward occurrence is a new instance of the
routine, not the same dormant plan — it deserves its own future check-in
rather than inheriting "already asked" state from the prior occurrence.

## Alternatives considered

### Recurring nudges (ask again every N hours/days until resolved)

Simpler mental model — like the reminder scheduler, just keep polling.

**Rejected:** directly violates "respectful by default, aggressive only on
permission." A plan that's already stale and gets asked about repeatedly
is exactly the nagging-todo-list experience the PRD explicitly rejects.

### A UI badge/banner instead of push + conversation turn

Surface staleness passively in the commitment list (e.g., a "quiet since
Tuesday" badge) rather than proactively asking.

**Rejected (for now):** passive surfacing requires the user to open the
app and notice it — it doesn't re-engage someone who's stopped opening
the app, which is the exact failure mode (neglect) this feature targets.
Proactive push + a conversational ask does the re-engaging. A passive
badge is a reasonable complementary addition later, not a replacement.

### In-memory dedup (mirror ReminderScheduler exactly)

Track "asked" commitment ids in a process-local set, like
`ReminderScheduler._notified_ids`.

**Rejected:** a process restart would reset the set and re-ask about every
still-dormant commitment — directly breaking the "fires once per
commitment, ever" guarantee. The DB column is the only place that
guarantee can actually live.

### A generic "outcome" field the LLM writes free text into

Skip structured classification; just log whatever the user says as a note
on the commitment.

**Rejected:** doesn't let the app actually act (abandon status, reschedule
due_at) — it would just accumulate unread notes, no different from doing
nothing.

## Consequences

### Positive

- **Re-engagement without nagging.** Dormant plans get exactly one
  respectful nudge, ever — matching the PRD's core problem statement and
  its non-negotiable tone rules.
- **Works without push.** The conversation-turn fallback means the
  guarantee holds even for users who never granted notification
  permission (or are using a browser where push isn't configured at all).
- **Agency-preserving.** Every outcome is either "no change" or something
  the user explicitly said (abandon, reschedule) — never an auto-decision.
- **Persisted dedup survives restarts and multi-instance deploys** (a
  DB column, not per-process memory).
- **Clean interaction with recurrence** — roll-forward correctly resets
  the check-in state for the new occurrence.

### Negative

- **One more LLM call in the chat hot path** when a check-in is pending —
  adds latency to the user's very next message after a dormant-plan ask.
  Acceptable: it only happens when a check-in is actually pending, which
  is rare relative to total chat volume.
- **Batch-reply simplification.** Applying one outcome to all pending
  check-ins at once means a user can't (in one message) say "abandon the
  first one but reschedule the second" — they'd need to address them
  separately across messages. Fine for v1; revisit if multi-pending
  becomes common.
- **First-tick suppression means a genuinely fresh deploy always "loses"
  one batch of already-dormant items** without asking about them (they're
  silently marked sent). Same accepted tradeoff as `ReminderScheduler`'s
  identical pattern.
- **Threshold is global, not per-user or per-commitment-type.** A 4-hour
  quiet window may be too eager for some workflows and too lax for others.
  Configurable via `STALE_CHECK_THRESHOLD_HOURS`, not yet per-user.

### Future considerations

- Per-user configurable threshold (settings UI).
- Passive UI surfacing (a "quiet since X" badge) as a complement to the
  proactive ask.
- Per-item outcome when multiple check-ins are pending at once.
- Extending the outcome set (e.g., "snooze the check-in itself" distinct
  from "reschedule the due date").

## References

- `docs/PRD.md` — "recall, never judgment," agency, respectful-by-default
- ADR-0015 — recurring commitments via roll-forward (the interaction this
  feature has to account for)
- ADR-0004 — briefing caching (the closest prior art for "ask once, don't
  repeat unnecessarily" thinking, though a different mechanism)
- `backend/app/services/stale_check_scheduler.py`
- `backend/app/services/chat_service.py` (`_handle_stale_check_reply`)
- `backend/app/prompts/stale_check_reply.py`
- `backend/migrations/009_stale_check.sql`
