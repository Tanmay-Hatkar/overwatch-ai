# 0024: Mobile-only client — remove the web app, Capacitor wrapper, and web-only backend paths

- **Status:** Accepted
- **Date:** 2026-10-09
- **Deciders:** Tanmay Hatkar

## Context

ADR-0023 made mobile-first the design default, but the repo still carried
three clients for one product:

1. `frontend/` — the React + Vite web SPA (~4,100 lines).
2. `frontend/android/` — a Capacitor wrapper around that SPA, which the
   PRD still called "the primary product."
3. `mobile/` — the React Native / Expo app, where all recent product work
   landed (AI-first capture, Tier-2 ring escalation, home-screen widget, PR #16).

The author confirmed `mobile/` is the product. CI had already stopped
testing `frontend/` — only `backend` and `mobile` jobs run — so the web app
was abandoned in practice but still cost attention: duplicate logic,
docs describing the wrong client, and backend code paths (cookie sessions,
redirect-to-frontend, Capacitor CORS origins, Web Push) that only the web
client used.

An audit of `mobile/src/api.js` shows the app calls exactly: `/commitments`
(CRUD), `/chat`, `/chat/history`, `/briefings/today`, `/reflections/today`,
`/auth/me`, `/auth/logout`, and `/auth/google/login?native=1`.

## Decision

**`mobile/` is the only client.** Remove everything that exists only to
serve another client:

1. **Delete `frontend/`** — the web SPA and the Capacitor Android project.
2. **Bearer-only auth.** Sessions travel as `Authorization: Bearer <jwt>`.
   The session cookie, cookie refresh (`should_refresh`,
   `session_refresh_within_days`), `session_cookie_name`, `frontend_url`,
   and the redirect-to-frontend branch of the OAuth callback are removed.
   Every OAuth flow now deep-links to `overwatch://auth`. The short-lived
   OAuth *state* cookie stays — it lives in the system browser for the
   few seconds of sign-in and is the CSRF check. `/auth/logout` stays as a
   stateless 204 so the app keeps a stable hook.
3. **Remove the browser-based Google Calendar connect flow**
   (`/calendar/connect/google` + callback, `google_calendar_oauth.py`).
   Its callback authenticated the user with the web session cookie, which
   the mobile app never has, so it could not work from mobile. Calendar
   *reading* (providers, stored-token repository, `/calendar/*` display
   routes, the briefing's calendar hook) is kept as the seam a future
   mobile connect flow would plug into.
4. **CORS** keeps only `CORS_ORIGINS` (default `http://localhost:8081`,
   Expo web). The Capacitor origins and `allow_credentials` are gone —
   native fetches aren't subject to CORS, and no cookie is sent.
5. **Remove Web Push** (VAPID keys, `/push/*`, push service/repository,
   `pywebpush`) in a follow-up PR. Mobile reminders are scheduled on-device
   with `expo-notifications` and the ring-alarm native module (ADR-0019),
   and the stale-plan check-in is delivered as a conversation turn the app
   reads (ADR-0017); neither uses Web Push.

The pre-removal tree is tagged **`pre-mobile-only`**. Provenance comments in
`mobile/` that cite `frontend/src/...` refer to files at that tag.

## Alternatives considered

- **Keep the web app as an optional companion.** Rejected — CI already
  didn't test it, nothing in the v1 scope needs a desktop surface (PRD §9),
  and every backend change would keep paying for cookie + bearer dual
  paths. It is one `git checkout pre-mobile-only -- frontend` away.
- **Keep cookie auth "just in case."** Rejected — dead auth code is risky
  code; two token sources is a larger surface to reason about than one.
- **Rebuild calendar connect for mobile now.** Deferred — it needs a
  callback that identifies the user without a cookie (e.g. a signed
  `state` carrying the user id), and calendar is background context only
  (ADR-0022). Not worth building before the core loop is validated.
- **Cut calendar entirely.** Deferred to the author. Note for that
  decision: the briefing's calendar context uses the default, non-user
  provider (Empty in production), so calendar currently contributes
  nothing to production briefings either way.

## Consequences

### Positive

- One client, one auth mechanism, one set of docs to keep true.
- Removes ~4,100 lines of frontend plus the backend paths only it used.
- New contributors (and Claude) no longer have to work out which of three
  apps is the real one.

### Negative

- No web or desktop access to Overwatch. Accepted per PRD §6/§9.
- Users with an existing *web* session must sign in again on mobile
  (mobile already used bearer tokens, so mobile users are unaffected).
- Sessions no longer silently refresh; the app signs in again when its
  30-day token expires (this was already true for mobile).
- Google Calendar can't be connected until a mobile connect flow exists.

## References

- ADR-0023 — v1 refocus, mobile-first (this ADR completes it)
- ADR-0005, ADR-0007, ADR-0012 — browser reminders, Web Push, Web Speech
  API: superseded for the product by this ADR (the web client is gone)
- ADR-0009 — Google OAuth (cookie half superseded; bearer half stands)
- ADR-0011 — per-user calendar OAuth (connect flow removed; storage kept)
- ADR-0017, ADR-0019 — stale check + ring escalation (mobile delivery)
- Tag `pre-mobile-only` — last commit with the web app
