-- Migration 009 — Stale-plan detection
--
-- Adds two nullable timestamp columns to commitments to support a
-- "recall, never judgment" check-in: once a plan has gone quiet, we ask
-- "still the plan?" ONCE — ever — instead of nagging on every poll.
--
-- stale_check_sent_at: when we asked. NULL = never asked yet (or not
--   dormant enough to qualify). Once set, StaleCheckScheduler never
--   re-asks about this row again (see docs/adr/0017-stale-plan-detection.md).
-- stale_check_acknowledged_at: when the user's reply to the check-in was
--   processed (any outcome). NULL = still pending — ChatService intercepts
--   the user's next message while this is NULL and this column is set once
--   the outcome (still_valid/abandon/reschedule/unrelated) is applied.
--
-- A recurring commitment that rolls forward to its next occurrence
-- (ADR-0015) is a NEW instance, not the same dormant plan — the service
-- layer clears both columns back to NULL on roll-forward.

ALTER TABLE commitments ADD COLUMN stale_check_sent_at TEXT DEFAULT NULL;
ALTER TABLE commitments ADD COLUMN stale_check_acknowledged_at TEXT DEFAULT NULL;
