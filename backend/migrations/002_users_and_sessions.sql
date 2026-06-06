-- Migration 002 — Users table for authentication (Slice 11)
--
-- Adds the users table for Google OAuth-based authentication.
-- Adding user_id columns to existing tables happens in migration 003
-- (Slice 12, multi-tenancy). This migration only stands up the auth
-- foundation.
--
-- Columns:
--   id          UUID (TEXT). Stable internal identifier.
--   google_id   The "sub" claim from Google's id_token. Immutable.
--   email       User's email (from Google). Indexed for lookup.
--   name        Display name from Google profile.
--   picture     Profile picture URL from Google (optional).
--   created_at  ISO 8601 timestamp.
--   last_login_at  ISO 8601 timestamp of most recent /auth/me success.

CREATE TABLE IF NOT EXISTS users (
    id              TEXT PRIMARY KEY,
    google_id       TEXT NOT NULL UNIQUE,
    email           TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    picture         TEXT,
    created_at      TEXT NOT NULL,
    last_login_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_google_id ON users(google_id);
