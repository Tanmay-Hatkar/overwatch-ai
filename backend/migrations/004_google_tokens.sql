-- Migration 004 — Per-user Google OAuth tokens (Slice 12)
--
-- Each user authorizes their own Google Calendar by going through a
-- separate OAuth flow with the Calendar scopes (handled by routes
-- added in this slice). Their access/refresh tokens land here, one
-- row per user.
--
-- This replaces the single shared backend/token.json used during
-- single-user development. The Calendar provider reads from this
-- table per request, refreshing expired access tokens transparently.
--
-- ON DELETE CASCADE: removing a user wipes their stored Google
-- credentials immediately (GDPR-friendly default).

CREATE TABLE IF NOT EXISTS google_tokens (
    user_id        TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    access_token   TEXT NOT NULL,
    refresh_token  TEXT,
    token_uri      TEXT NOT NULL DEFAULT 'https://oauth2.googleapis.com/token',
    client_id      TEXT NOT NULL,
    client_secret  TEXT NOT NULL,
    scopes         TEXT NOT NULL,
    expiry         TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);
