# 0014: Per-user conversation memory in the database

- **Status:** Accepted
- **Date:** 2026-06-11
- **Deciders:** Tanmay Hatkar

## Context

Chat history lived only in the browser's `localStorage` (ADR-0008's
deliberate MVP choice). With multi-tenancy shipped (ADR-0013), each user
now has isolated commitments and the assistant reads only their data — but
their *conversation* still didn't persist server-side. Consequences:

- History was per-device: open Overwatch on your phone and your laptop's
  conversation context was gone.
- Clearing the browser wiped the context entirely.
- The backend received history from the client on every request and
  trusted it — fine for one device, but not a durable per-user memory.

The user's request was explicit: conversation context should be saved per
user, server-side, so it follows them.

## Decision

**Persist each conversation turn in a `conversation_turns` table keyed by
user_id. The chat service loads the recent tail from the DB to build prompt
context and appends both turns after each exchange. The frontend loads
history from the server on mount, with localStorage kept only as an offline
cache.**

### Schema (migration 005)

```sql
CREATE TABLE conversation_turns (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role        TEXT NOT NULL,      -- 'user' | 'assistant'
    content     TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE INDEX idx_conversation_turns_user ON conversation_turns(user_id, created_at);
```

One row per message. `ON DELETE CASCADE` wipes a user's history with their
account.

### Flow

- `ConversationRepository.recent(user_id, limit)` returns the newest N turns
  in chronological order (newest-by-rowid then reversed — rowid is a stable
  monotonic tiebreaker within the same timestamp).
- `ChatService.handle()` loads `recent(user_id, 10)` as context, calls the
  LLM, then `append()`s the user message and the assistant reply.
- New endpoints: `GET /chat/history` (load) and `DELETE /chat/history`
  (clear). Both `current_user`-scoped.
- The frontend `ChatBar` fetches `/chat/history` on mount (authoritative),
  seeding from localStorage first for an instant paint; "clear" calls
  `DELETE /chat/history`.

### Backward compatibility

`ChatService`'s `conversation_repo` is **optional**. When absent (existing
unit tests that construct the service directly), it falls back to the
client-supplied `request.history`, so nothing breaks. The route always
wires the repo in production.

## Alternatives considered

### Keep localStorage only (status quo)

**Rejected:** the whole point was cross-device, durable memory. localStorage
is per-device by definition.

### Summarize old turns into a rolling memory instead of storing raw turns

A "memory" that compresses old conversation into a summary to save tokens.

**Rejected for now:** premature. We cap context at the last 10 turns
already, which is cheap. Raw turns are simpler, debuggable, and we can add
summarization later if histories grow long enough to matter.

### Store full history client-side but sync to a backend blob

Push the localStorage array to a per-user row as an opaque JSON blob.

**Rejected:** a real table with one row per turn is queryable, indexable,
paginatable, and cascades on user delete. A blob is none of those.

## Consequences

### Positive

- **Cross-device memory.** Sign in anywhere; your conversation context is
  there.
- **Survives cleared browsers.** The server is the source of truth.
- **Server-grounded context.** The prompt's conversation context no longer
  depends on the client sending (or tampering with) history.
- **Clean delete path.** `DELETE /chat/history` + cascade on user delete.
- **Backward compatible.** Optional repo keeps existing tests/callers valid.

### Negative

- **Storage grows with use.** One row per message. Unbounded over time;
  fine for now, would want a retention policy (or summarization) at scale.
- **A DB write per turn.** Two inserts per exchange. Negligible at our
  volume; SQLite handles it easily.
- **Still single-device for the *display* cache.** localStorage holds the
  last-seen copy per device; the server reconciles it on next load.

### Future considerations

- Retention / summarization once histories get long.
- Pagination for `GET /chat/history` (currently a simple recent-N).
- Use stored history for longer-term recall ("what did I say about the
  proposal last week?") — would need retrieval over the full history, not
  just the recent tail.

## References

- ADR-0008 — original chat design (localStorage history)
- ADR-0013 — multi-tenancy (the user scoping this builds on)
- `backend/migrations/005_conversation_turns.sql`
- `backend/app/repositories/conversation_repository.py`
- `backend/app/services/chat_service.py`
- `backend/app/routes/chat.py`
- `frontend/src/components/ChatBar.jsx`
