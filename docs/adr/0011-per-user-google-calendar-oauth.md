# 0011: Per-user Google Calendar via in-app OAuth, DB-stored tokens

- **Status:** Accepted
- **Date:** 2026-06-07
- **Deciders:** Tanmay Hatkar

## Context

The weekly calendar grid is a core part of the home view, but on the
deployed app it was empty: the original `GoogleCalendarProvider` reads
credentials from a `token.json` file on disk, produced by a one-time
local script (`scripts/setup_google_oauth.py`). That file is gitignored
and machine-local — it doesn't exist on Railway, so production fell back
to `EmptyCalendarProvider` (an honest empty grid).

To show real events on the hosted app, the user must be able to connect
their Google Calendar **from the browser**, and the resulting tokens
must persist server-side across container restarts.

We already have:
- Google OAuth for *login* (`google_oauth_service`, openid/email/profile
  scopes, no stored tokens — we mint our own JWT)
- A `users` table + `current_user` dependency (ADR-0009)
- A `GoogleCalendarProvider` that knows how to talk to the Calendar API
  given credentials

What was missing: a *calendar* OAuth flow (offline access, refresh token,
`calendar.readonly` scope) and somewhere to store the tokens.

## Decision

**An in-app OAuth flow that requests `calendar.readonly` with offline
access, stores the resulting tokens in a `google_calendar_tokens` table
keyed by user_id, and a `GoogleCalendarProvider` that builds its client
from that row (refreshing + persisting tokens as needed).**

### Scope + client

- Reuse the existing `overwatch-web` OAuth client (same one used for
  login). Calendar access is requested as an *incremental* scope, so the
  user has a single client and a single app on the consent screen.
- Request only `https://www.googleapis.com/auth/calendar.readonly` — we
  never write to the user's calendar.
- `access_type=offline` + `prompt=consent` so Google returns a refresh
  token (needed to keep reading events after the 1-hour access token
  expires).

### Flow

```
Browser                         Backend                         Google
  │ ── GET /calendar/connect/google ──▶                          │
  │   (current_user required)         │ ── build auth URL ──────▶ │
  │ ◀── 302 to Google (calendar scope)│                          │
  │ ── user grants calendar access ───────────────────────────▶  │
  │ ◀── 302 /calendar/connect/google/callback?code=… ─────────── │
  │ ── GET callback ─▶                │ ── POST /token ─────────▶ │
  │                                   │ ◀── access+refresh token ─│
  │                                   │  (store row for user_id)  │
  │ ◀── 302 to frontend (?calendar=connected) ──                 │
```

### Storage

`google_calendar_tokens` holds access_token, refresh_token, token_uri,
client_id, client_secret, scopes, expiry — everything
`google.oauth2.credentials.Credentials` needs to reconstruct itself and
self-refresh. The provider writes the row back after a refresh so the
new access token is reused next time.

### Provider construction (per-user, per-request)

The calendar *display* routes (`/calendar/today`, `/calendar/week`) now
resolve `current_user`, look up that user's token row, and build a
`GoogleCalendarProvider` from it. If the user has no row:
- production → `EmptyCalendarProvider` (honest empty grid)
- development → `MockCalendarProvider` (visible test data)

A `GET /calendar/connection` endpoint reports `{connected: bool}` so the
frontend knows whether to show the "Connect Google Calendar" CTA or the
events.

## Alternatives considered

### Keep token.json, upload it to Railway as a secret/volume file

Bundle the developer's personal token as a deployed secret.

**Rejected because:**
- It hard-codes ONE person's calendar into the deploy — can't generalize
  to other users, and rotating/revoking is manual
- Tokens in env vars/secret files are awkward to refresh (the provider
  needs to write the refreshed token somewhere persistent)
- The in-app flow is the same amount of work and is the real solution

### Full multi-tenancy first (slice 12), then calendar

Do the complete `user_id`-scoping refactor across every table, then add
calendar.

**Rejected (for now) because:**
- That's a 2-3 day refactor; calendar-on-the-grid is the single most
  visible win and is achievable in hours
- This table is *already* keyed by user_id, so it's forward-compatible —
  when full multi-tenancy lands, this slots in unchanged
- We deliberately keep the blast radius small: only the calendar display
  routes become per-user; briefings/commitments/push are untouched

### Store tokens in a file on the Railway volume

Write `token.json` to `/data` instead of the DB.

**Rejected because:**
- The DB already lives on the volume and has transactions + the user FK
- One storage mechanism is simpler than two
- Per-user file management (one file per user) is clumsier than rows

## Consequences

### Positive

- **Real events on the grid.** Connect once, see your actual calendar.
- **Survives restarts.** Tokens in the DB (on the Railway volume) persist.
- **Forward-compatible.** Table keyed by user_id; drops straight into
  full multi-tenancy later.
- **Self-refreshing.** Expired access tokens refresh transparently and
  the new token is persisted.
- **Revocable.** A `disconnect` deletes the row; cascade on user delete.
- **Minimal blast radius.** Only calendar display routes change; the rest
  of the app is untouched.

### Negative

- **Briefings don't include calendar events yet.** The briefing route
  still uses the default (Empty/Mock) provider singleton because it isn't
  user-scoped on `main` yet. After connecting, the grid shows events but
  the morning briefing won't mention them until briefings become
  user-scoped (slice 12). Acceptable interim gap; noted as a follow-up.
- **A new GCP redirect URI must be registered** for the calendar callback
  (`{BACKEND_URL}/calendar/connect/google/callback`). Documented in
  DEPLOYMENT.md.
- **Tokens are sensitive at rest.** They live in the SQLite file on the
  Railway volume. Not encrypted at the column level (out of scope for a
  single-user private deploy); revisit if we store many users' tokens.
- **Consent screen shows calendar access.** Slightly heavier consent than
  login alone — expected and appropriate.

### Future considerations

- User-scope briefings so the morning summary includes calendar events.
- Column-level encryption of tokens once multi-user.
- Multiple calendars (work + personal) — the provider already takes a
  `calendar_id`; would need a list + per-calendar rows.
- Incremental sync (Google `syncToken`) instead of re-fetching the week.

## References

- ADR-0006 — calendar provider abstraction (the seam this plugs into)
- ADR-0009 — Google OAuth for login (the pattern this mirrors)
- `backend/migrations/003_google_calendar_tokens.sql`
- `backend/app/services/google_calendar_oauth.py`
- `backend/app/repositories/google_calendar_tokens_repository.py`
- `backend/app/routes/calendar.py`
- [Google OAuth incremental authorization](https://developers.google.com/identity/protocols/oauth2/web-server#incrementalAuth)
