-- Migration 003 — Multi-tenancy (Slice 12)
--
-- Adds user_id foreign keys to every user-owned table. After this
-- migration, all user-owned data is row-level-scoped to a specific user.
--
-- Backfill: if exactly ONE user exists at migration time, all existing
-- rows are assigned to that user. This is the case on a developer's
-- local DB where commitments predate authentication. In a fresh
-- production deploy (zero users at migration time), this is a no-op.
--
-- The user_id column is nullable at this point. We do NOT add NOT NULL
-- because SQLite doesn't support adding a NOT NULL constraint to an
-- existing column without a full table rebuild. That tightening
-- happens in slice 13 during the Postgres migration where it's a
-- one-liner. In the meantime, every repository write SETS user_id
-- explicitly, and every read FILTERS by user_id, so NULL rows would
-- be invisible to the app — but the orphan-row scenario can't arise
-- post-backfill.

ALTER TABLE commitments         ADD COLUMN user_id TEXT;
ALTER TABLE briefings           ADD COLUMN user_id TEXT;
ALTER TABLE push_subscriptions  ADD COLUMN user_id TEXT;

CREATE INDEX IF NOT EXISTS idx_commitments_user_id        ON commitments(user_id);
CREATE INDEX IF NOT EXISTS idx_briefings_user_id          ON briefings(user_id);
CREATE INDEX IF NOT EXISTS idx_push_subscriptions_user_id ON push_subscriptions(user_id);

-- Backfill: only fires when exactly one user exists. The subquery
-- returns NULL if there are zero or 2+ users, which UPDATE happily
-- writes as NULL (so existing rows stay NULL in those cases — but
-- production starts with zero users so this is the right behavior).
UPDATE commitments
   SET user_id = (
       SELECT id FROM users
       LIMIT 2  -- if there's more than one, subquery resolves ambiguously; protect below
   )
 WHERE user_id IS NULL
   AND (SELECT COUNT(*) FROM users) = 1;

UPDATE briefings
   SET user_id = (SELECT id FROM users LIMIT 2)
 WHERE user_id IS NULL
   AND (SELECT COUNT(*) FROM users) = 1;

UPDATE push_subscriptions
   SET user_id = (SELECT id FROM users LIMIT 2)
 WHERE user_id IS NULL
   AND (SELECT COUNT(*) FROM users) = 1;

-- The unique constraint on briefings.date is wrong post-multi-tenancy:
-- two users can both have a briefing for the same date. Drop and replace
-- with a composite UNIQUE(user_id, date).
--
-- SQLite doesn't support DROP CONSTRAINT directly. We use the standard
-- table-rebuild pattern: rename old, create new with the right
-- constraints, copy data, drop old.

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

INSERT INTO briefings_new (id, user_id, date, content, today_count, overdue_count, generated_at)
     SELECT id, user_id, date, content, today_count, overdue_count, generated_at
       FROM briefings;

DROP TABLE briefings;
ALTER TABLE briefings_new RENAME TO briefings;
CREATE INDEX IF NOT EXISTS idx_briefings_user_id ON briefings(user_id);
