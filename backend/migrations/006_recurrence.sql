-- Migration 006 — Recurring commitments (routines)
--
-- Adds a `recurrence` column so a commitment can repeat: 'none' (a one-off,
-- the default), 'daily', or 'weekly'. When a recurring commitment is marked
-- done, the service rolls its due_at forward to the next occurrence and keeps
-- it open — so a daily routine reappears tomorrow instead of vanishing.
--
-- Existing rows default to 'none' (unchanged behavior).

ALTER TABLE commitments ADD COLUMN recurrence TEXT NOT NULL DEFAULT 'none';
