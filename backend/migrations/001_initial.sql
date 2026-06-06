-- Migration 001 — Initial schema
--
-- The tables that existed before the migration system was introduced.
-- Captured here so a fresh database (e.g. a new dev clone or a new
-- production environment) reaches the same state as an existing one.
--
-- Idempotent (CREATE TABLE IF NOT EXISTS) so it's safe to re-run.

CREATE TABLE IF NOT EXISTS commitments (
    id          TEXT PRIMARY KEY,
    text        TEXT NOT NULL,
    due_at      TEXT,
    status      TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS briefings (
    id            TEXT PRIMARY KEY,
    date          TEXT NOT NULL UNIQUE,
    content       TEXT NOT NULL,
    today_count   INTEGER NOT NULL,
    overdue_count INTEGER NOT NULL,
    generated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS push_subscriptions (
    id          TEXT PRIMARY KEY,
    endpoint    TEXT NOT NULL UNIQUE,
    p256dh      TEXT NOT NULL,
    auth        TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
