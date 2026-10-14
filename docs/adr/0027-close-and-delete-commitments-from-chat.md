# 0027: Close and delete commitments from chat with one `close_commitment` intent

- **Status:** Accepted
- **Date:** 2026-10-13
- **Deciders:** Tanmay Hatkar

## Context

Chat could create and edit commitments but not end them. Asked to delete
items, the assistant replied "I can't delete items, but let me know the new
tasks you'd like to add for today": the request fell through to `general`.
"Did it", "never mind X" and "delete X" are the most natural things to say
to a commitment tracker, and the app's whole interface is chat. Ending a
commitment was only possible through the list UI (`PATCH` / `DELETE
/commitments/{id}`).

Two kinds of ending exist. Closing (done, or abandoned by choice) keeps a
record, which the evening reflection and stale-plan check-in rely on.
Deleting removes a row permanently, and is right for items added by mistake.
Abandoning was previously only reachable through the stale-plan check-in
(ADR-0017).

## Decision

Add one chat intent, `close_commitment`, with:

- `target_commitment_ids`: one or more ids from the existing "Editable
  commitments" prompt block (the single `target_commitment_id` field is also
  accepted, because models reuse `modify_commitment`'s shape);
- `close_action`: `done` | `abandoned` | `deleted`.

`done` and `abandoned` go through `CommitmentService.update`, so a recurring
commitment marked done rolls forward as it does from the checkbox. `deleted`
calls `CommitmentService.delete`. The prompt only allows `deleted` when the
user explicitly says delete / remove / erase / clear, and requires `clarify`
(`confirm_target` chips) when more than one item could match.

Guards in `ChatService`, independent of the model:

- Each id must be an open commitment owned by the user; anything else is
  skipped.
- One message closes at most `chat_max_close_targets` (default 10), so a
  misread "clear it all" can't wipe a whole list.
- If nothing could be applied, the reply is replaced with an honest one,
  the same pattern as goals (ADR-0026).

`ChatResponse` gains `closed` (the commitments as they were just before
closing) and `close_action`, and the mobile chat shows a small tag such as
"🗑 Deleted: Do laundry, Hit the gym".

The prompt's `general` rule also now says: if you can't do something, say
so in one sentence, and don't steer the user toward adding tasks.

## Alternatives considered

- **Three intents (`complete_` / `abandon_` / `delete_commitment`):**
  rejected. Same target-finding logic three times, and about three times the
  prompt growth on a ~6k-token prompt that already hits Groq's free-tier
  limit.
- **Only status changes, no hard delete:** rejected. Mistakenly added items
  would clutter the list and the reflection, and the user's first ask was
  literally "delete".
- **Confirmation turn before every delete:** rejected for now. It doubles
  the LLM calls (one per minute on Groq's free tier), and the unambiguous
  case is the common one. Ambiguous targets already go through `clarify`.
- **Soft delete with undo:** deferred. It needs a schema change (a
  `deleted_at` column, plus filtering everywhere). Worth doing if a wrong
  delete actually happens in use.

## Consequences

### Positive

- Every lifecycle action is reachable from chat: add, edit, done, drop, delete.
- Abandoning is no longer locked behind the stale-plan check-in.
- Server-side guards (scoping, open-only, cap) bound the damage of a
  hallucinated id.

### Negative

- A delete from chat is permanent. A wrong target is unrecoverable until
  undo exists; the guard against this is the prompt's `clarify` rule.
- The system prompt grows by about 500 tokens.

## References

- `backend/app/services/chat_service.py` (`_close_commitments`)
- `backend/app/prompts/chat.py` (intent 8)
- ADR-0017 (stale-plan abandon), ADR-0026 (honest fallback reply pattern)
