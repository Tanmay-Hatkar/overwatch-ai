-- Migration 003 — Per-user Google Calendar OAuth tokens
--
-- Stores the OAuth credentials each user grants when they connect their
-- Google Calendar (the "Connect Google Calendar" button). One row per
-- user. Replaces the single, machine-local token.json used during early
-- development — the hosted app has no filesystem token, so credentials
-- live in the database instead.
--
-- The GoogleCalendarProvider builds its API client from this row and
-- writes the row back when it refreshes an expired access token.
--
-- ON DELETE CASCADE: deleting a user wipes their stored Google
-- credentials immediately (a sensible privacy default).
--
-- Note: access_token / refresh_token are sensitive. They live only in
-- the database (gitignored SQLite file / Railway volume), never in the
-- repo. Disconnecting calendar deletes the row.

CREATE TABLE IF NOT EXISTS google_calendar_tokens (
    user_id        TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    access_token   TEXT NOT NULL,
    refresh_token  TEXT,
    token_uri      TEXT NOT NULL DEFAULT 'https://oauth2.googleapis.com/token',
    client_id      TEXT NOT NULL,
    client_secret  TEXT NOT NULL,
    scopes         TEXT NOT NULL,
    expiry         TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);
