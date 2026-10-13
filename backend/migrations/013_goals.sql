-- Migration 013 — Weekly rate goals (ADR-0026)
--
-- A goal is a count per calendar week: "10 job applications", "gym 4x".
-- Progress is never stored as a counter — it's the sum of goal_logs whose
-- logged_at falls inside the user's current week, so changing timezone or
-- undoing a log can't leave a stale total behind, and a new week starts
-- at zero by construction (no carryover, no streak history; ADR-0023).
--
-- The end-of-week check-in is asked once per week (PRD §4.3/§4.5). The
-- user's answer is stored as (decision, decision_week): decision is
-- 'keep_going' or 'call_it_good', decision_week the Monday (YYYY-MM-DD,
-- user-local) it applies to. It only ever affects the week it names.

CREATE TABLE IF NOT EXISTS goals (
    id            TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL,
    text          TEXT NOT NULL,
    target_count  INTEGER NOT NULL CHECK (target_count > 0),
    status        TEXT NOT NULL DEFAULT 'active',
    decision      TEXT,
    decision_week TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_goals_user_id ON goals(user_id);

CREATE TABLE IF NOT EXISTS goal_logs (
    id         TEXT PRIMARY KEY,
    goal_id    TEXT NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
    user_id    TEXT NOT NULL,
    amount     INTEGER NOT NULL CHECK (amount > 0),
    logged_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_goal_logs_goal_time ON goal_logs(goal_id, logged_at);
