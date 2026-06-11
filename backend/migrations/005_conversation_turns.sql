-- Migration 005 — Per-user conversation memory
--
-- Until now, chat history lived only in the browser's localStorage — it was
-- per-device and never reached the server. This table persists each
-- conversation turn server-side, keyed by user, so a user's chat context
-- follows them across devices and survives a cleared browser.
--
-- One row per message (user OR assistant). The chat service appends both
-- turns after each exchange and loads the recent tail to build prompt
-- context. ON DELETE CASCADE wipes a user's history when their account is
-- deleted.

CREATE TABLE IF NOT EXISTS conversation_turns (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role        TEXT NOT NULL,      -- 'user' | 'assistant'
    content     TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

-- Composite index supports the hot query: "this user's turns, newest first".
CREATE INDEX IF NOT EXISTS idx_conversation_turns_user
    ON conversation_turns(user_id, created_at);
