-- Migration 012 — Drop Web Push subscriptions (ADR-0024)
--
-- Web Push only served the removed web client. Mobile reminders are
-- scheduled on-device (expo-notifications + the ring-alarm module) and the
-- stale-plan check-in is delivered as a conversation turn, so these rows
-- are browser endpoints nothing will ever send to again.

DROP INDEX IF EXISTS idx_push_subscriptions_user_id;
DROP TABLE IF EXISTS push_subscriptions;
