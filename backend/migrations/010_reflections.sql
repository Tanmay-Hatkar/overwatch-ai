-- Migration 010 — Evening reflection cache
--
-- Mirrors migration 004's briefings table shape: one persisted reflection
-- per (user_id, date), regenerated when commitments change since it was
-- generated (see ADR-0004's caching strategy, reused here per
-- docs/adr/0018-evening-reflection.md).
--
-- user_id is nullable for the same reason briefings.user_id is (see
-- migration 004) — every write stamps it, and the app never queries
-- without a user_id filter, so NULL rows are simply invisible rather than
-- a leak risk.

CREATE TABLE IF NOT EXISTS reflections (
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

CREATE INDEX IF NOT EXISTS idx_reflections_user_id ON reflections(user_id);
