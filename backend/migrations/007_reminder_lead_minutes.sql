-- Migration 007 — Per-commitment reminder lead time
--
-- Adds `reminder_lead_minutes`: how many minutes BEFORE due_at to nudge.
--   0  = fire exactly at the time (an alarm, e.g. "wake me at 2pm") — default
--   >0 = a heads-up that many minutes before (e.g. a meeting)
--
-- The LLM sets it from the user's phrasing; it's editable per item. The
-- on-device notification is scheduled at (due_at - reminder_lead_minutes).
-- Existing rows default to 0 (exact), preserving current behavior.

ALTER TABLE commitments ADD COLUMN reminder_lead_minutes INTEGER NOT NULL DEFAULT 0;
