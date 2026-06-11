-- Migration 004 — Multi-tenancy: scope user-owned data by user_id (Slice 12)
--
-- Until now the app had login (users table) but commitments, briefings, and
-- push subscriptions were GLOBAL — every signed-in account shared one pool.
-- This migration adds a user_id foreign key to each user-owned table so each
-- user's data is isolated. After this, every repository read filters by
-- user_id and every write stamps it.
--
-- Backfill: if exactly ONE user exists at migration time (the developer's
-- own account on the existing deploy), all pre-existing rows are assigned to
-- that user so nothing is orphaned. In a fresh deploy (zero users) this is a
-- no-op. With 2+ users we can't guess ownership, so rows stay NULL — and
-- since every query filters by user_id, NULL-owned rows become invisible
-- rather than leaking across accounts.
--
-- user_id is left nullable: SQLite can't add a NOT NULL column to an existing
-- table without a full rebuild, and the app sets user_id on every write
-- anyway. The Postgres migration (when we get there) can tighten it.

ALTER TABLE commitments         ADD COLUMN user_id TEXT;
ALTER TABLE push_subscriptions  ADD COLUMN user_id TEXT;

CREATE INDEX IF NOT EXISTS idx_commitments_user_id        ON commitments(user_id);
CREATE INDEX IF NOT EXISTS idx_push_subscriptions_user_id ON push_subscriptions(user_id);

-- Backfill only when exactly one user exists. The subquery yields that user's
-- id; the guard `(SELECT COUNT(*) FROM users) = 1` keeps it a no-op otherwise.
UPDATE commitments
   SET user_id = (SELECT id FROM users LIMIT 1)
 WHERE user_id IS NULL
   AND (SELECT COUNT(*) FROM users) = 1;

UPDATE push_subscriptions
   SET user_id = (SELECT id FROM users LIMIT 1)
 WHERE user_id IS NULL
   AND (SELECT COUNT(*) FROM users) = 1;

-- Briefings need a user_id AND a different uniqueness rule: the old schema had
-- UNIQUE(date) (one briefing per day, globally). Now two users can each have a
-- briefing for the same date, so the constraint becomes UNIQUE(user_id, date).
-- SQLite can't alter a UNIQUE constraint in place, so we rebuild the table.

CREATE TABLE briefings_new (
    id            TEXT PRIMARY KEY,
    user_id       TEXT,
    date          TEXT NOT NULL,
    content       TEXT NOT NULL,
    today_count   INTEGER NOT NULL,
    overdue_count INTEGER NOT NULL,
    generated_at  TEXT NOT NULL,
    UNIQUE(user_id, date)
);

-- Copy existing briefings, backfilling user_id under the same single-user rule.
INSERT INTO briefings_new (id, user_id, date, content, today_count, overdue_count, generated_at)
     SELECT
         id,
         CASE WHEN (SELECT COUNT(*) FROM users) = 1
              THEN (SELECT id FROM users LIMIT 1)
              ELSE NULL END,
         date, content, today_count, overdue_count, generated_at
       FROM briefings;

DROP TABLE briefings;
ALTER TABLE briefings_new RENAME TO briefings;
CREATE INDEX IF NOT EXISTS idx_briefings_user_id ON briefings(user_id);
