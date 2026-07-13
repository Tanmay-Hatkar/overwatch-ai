# 0021: Natural reminder phrasing (`reminder_phrase`)

- **Status:** Accepted
- **Date:** 2026-07-13
- **Deciders:** Tanmay Hatkar

## Context

Overwatch's PRD names a specific mechanic for how a reminder should sound:
not a generic nudge, but a "specific recall" of what the user actually said,
framed as a question — *"You said you'd start interview prep at 2:30 —
starting?"* (PRD section 4, item 2, "Holds you to your own word").

Every reminder delivery path instead sends a templated concatenation of the
raw `text` field:

- Web push (`reminder_scheduler.py`): `f"You said you'd: {commitment.text}"`
- Android Tier-1 heads-up (`notifications.js`): `` `In ${lead}: ${text}` `` /
  `` `Time to start: ${text}` ``
- Android Tier-1 snooze reschedule: `` `Still pending: ${text}` ``
- Android Tier-2 ring escalation (ADR-0019): the raw `text` verbatim

`text` itself is already a concise imperative rephrasing produced by the
commitment parser (e.g. "Call mom", not the user's raw sentence), but it's
a task label, not a check-in — reminders end up sounding like an alarm
clock reading a to-do item back at you, not like a considerate assistant
recalling your own word. This is a real gap against the product's stated
core mechanic, not a cosmetic one.

## Decision

**Extend the commitment parser's existing single LLM call
(`commitment_parser_service.py` / `commitment_parser.py`) to also emit a
third field, `reminder_phrase` — a natural, specific-recall check-in line —
and use it at every reminder delivery site, falling back to the current
templated strings when it's absent (`None`).**

### Why generate it at parse (capture) time, not at delivery (fire) time

Two points during a commitment's life could generate this phrasing:

1. **At capture**, alongside `text`/`due_at`, in the same LLM call.
2. **At delivery**, via a fresh LLM call each time a reminder fires.

Chosen: (1), capture time.

**Rejected: rephrase at delivery/fire time via a second LLM call.**
- Adds a network dependency and latency to the reminder-firing path itself
  — `reminder_scheduler.py`'s poll tick and `RingAlarmReceiver`'s
  `BroadcastReceiver` (ADR-0019) are both meant to be fast and reliable;
  neither should block on an LLM round-trip (or its fallback chain, up to
  three providers deep — ADR-0002) to produce notification text.
- A commitment can fire multiple times (Tier-1, then Tier-2 escalation,
  then a snooze reschedule) — regenerating the phrase each time is
  wasteful and risks visibly different wording across the same commitment's
  firings, which reads as inconsistent rather than considerate.
- Everything the phrasing needs (`text`, `due_at`) is already fully known
  at capture time — there's no new information delivery time would add.

**Rejected: leave reminders as static templates.**
- Directly contradicts the PRD's own named mechanic (section 4, item 2).
  This is the whole point of "surgical follow-up," not a nice-to-have.

### Architecture

```
commitment_parser.py (prompt)
  → SYSTEM_PROMPT now asks for {text, due_at, reminder_phrase} in one call
commitment_parser_service.py
  → _extract_reminder_phrase(): lenient (log + None on missing/invalid),
    mirrors _extract_due_at()'s leniency — never fails the whole parse
    over this field
CommitmentCreate / CommitmentBase / CommitmentUpdate (models/commitment.py)
  → reminder_phrase: str | None, nullable, no default
commitment_repository.py / commitment_service.py
  → threaded through create()/update()/_row_to_response() exactly like
    group_name and reminder_lead_minutes were
migrations/011_reminder_phrase.sql
  → ALTER TABLE commitments ADD COLUMN reminder_phrase TEXT (nullable,
    NO default — see "Why no default" below)

Delivery (falls back to the pre-existing template when reminder_phrase is None):
  reminder_scheduler.py       → web push body
  notifications.js            → Android Tier-1 heads-up + snooze reschedule
                                 + Tier-2 ring escalation body
```

No native Android (Kotlin) changes: Tier-1/Tier-2 native code only renders
whatever `title`/`body` string the JS layer hands it (confirmed —
`ringAlarm.js` passes `title`/`body` straight through to
`RingAlarmPlugin.ring()`), so this is a JS + backend change only.

### Why no default (unlike `group_name`'s `DEFAULT ''`)

`group_name` defaults to `''` because "ungrouped" and "not set" are the
same state. Here they're different: `NULL` means "never generated,"
which every delivery site needs to distinguish from an actual (if
hypothetically empty) phrase, specifically so the fallback-to-template
logic and the backfill script both know which rows still need work.

### Existing commitments

`reminder_phrase` is only ever populated by the parser at creation time —
commitments created before this migration have it `NULL` forever unless
something else fills it in. `backend/scripts/backfill_reminder_phrases.py`
(via `ReminderPhraseBackfillService`) does that once, manually, post-deploy:
for each open commitment missing `reminder_phrase`, it makes one narrow LLM
call that takes the existing `text`/`due_at` as fixed context and asks only
for the phrase — it never re-derives or touches `text`/`due_at`, so it
cannot alter a working due date. Idempotent (only touches rows still
`NULL`), not wired into any scheduled job.

## Alternatives considered

- **Rephrase at delivery/fire time via a second LLM call** — see above;
  rejected for latency, reliability, and consistency reasons.
- **Leave reminders as static templates** — rejected; contradicts the PRD's
  named mechanic directly.
- **A single combined script that also re-parses `text`/`due_at`** for the
  backfill — rejected: re-running the full parser against already-correct
  data risks a subtly different `due_at` coming back (LLM non-determinism,
  even at `temperature=0`) and silently corrupting a working reminder time.
  Asking only for the one new field removes that risk entirely.

## Consequences

### Positive
- Reminders now match the PRD's actual target phrasing, at zero marginal
  LLM cost or latency (same parse call already being made).
- Every existing delivery site degrades gracefully (old template) for any
  commitment without a phrase — no behavior change for rows this doesn't
  reach yet, no breaking change to any existing test's expectations.
- Backfill is safe by construction (narrow input, single field written,
  idempotent) rather than by convention.

### Negative
- Existing open commitments don't get the new phrasing until the backfill
  script is run manually — a manual post-deploy step, not automatic.
- Phrasing quality is bounded by the same LLM reliability the parser
  already accepts (ADR-0002's fallback chain, ADR-0003's structured-output
  approach) — no new risk class, but not a new guarantee either.
- If a commitment's `text` is edited later via `PATCH /commitments/{id}`,
  its `reminder_phrase` is NOT regenerated — it can go stale relative to
  the new text. Out of scope for this slice; acceptable because `text`
  edits are comparatively rare next to creation, and a stale-but-still-
  sensible phrase is a minor UX rough edge, not a correctness bug.
- One more prompt-shaped JSON-with-markdown-fence-stripping parser now
  exists (`reminder_phrase_backfill_service.py`), following the same
  pattern already duplicated between `commitment_parser_service.py` and
  `chat_service.py` rather than a shared utility — consistent with this
  codebase's existing choice not to factor that out, but worth revisiting
  if a fourth occurrence shows up.

### Future considerations
- Regenerate `reminder_phrase` automatically when `text` or `due_at`
  changes via `PATCH`, so edited commitments don't carry stale phrasing.
- Vary phrasing by escalation tier (e.g. a firmer tone for the Tier-2 ring
  than the initial Tier-1 heads-up) rather than reusing the same phrase
  for both.
- Extract the markdown-fence-stripping JSON parse helper shared by
  `commitment_parser_service.py`, `chat_service.py`, and now
  `reminder_phrase_backfill_service.py` into one utility, if a fourth
  occurrence ever appears.

## References

- `docs/PRD.md` section 4, item 2 — "Holds you to your own word," the
  mechanic this closes the gap on.
- ADR-0002 — LLM provider fallback chain, reused unchanged here.
- ADR-0003 — prompt engineering for structured output, the pattern
  `reminder_phrase` follows.
- ADR-0019 — ring-alarm escalation; confirms native Android code only
  renders JS-supplied strings, hence no native changes here.
- `backend/app/prompts/commitment_parser.py` — the extended prompt.
- `backend/app/prompts/reminder_phrase_backfill.py` — the narrower backfill-only prompt.
- `backend/app/services/commitment_parser_service.py` — `_extract_reminder_phrase`.
- `backend/app/services/reminder_phrase_backfill_service.py` — the backfill logic.
- `backend/scripts/backfill_reminder_phrases.py` — the one-time run entry point.
- `backend/migrations/011_reminder_phrase.sql`
- `backend/app/services/reminder_scheduler.py` — web push delivery.
- `frontend/src/lib/notifications.js` — Android Tier-1/Tier-2 delivery.
