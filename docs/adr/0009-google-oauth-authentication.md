# 0009: Google OAuth authentication with JWT session cookies

- **Status:** Accepted
- **Date:** 2026-06-03
- **Deciders:** Tanmay Hatkar

## Context

Through slice 10, Overwatch was a single-user application. The
`commitments`, `briefings`, and `push_subscriptions` tables had no
`user_id` column. The Google Calendar token sat in a single
`token.json`. Every chat request was implicitly "the user."

This is the right shape for personal use, but the goal has changed:
**ship Overwatch to a URL where friends can sign in and each get their
own copy.** That requires three things, in order:

1. **Authentication** — a way to identify who's making a request.
2. **Multi-tenancy** — every existing piece of data scoped to a user.
3. **Per-user external state** — each user's own Google calendar token,
   their own push subscriptions, their own commitments.

This ADR covers (1). ADR-0010 covers (2) and (3).

The constraints on (1):

- **Low-friction sign-up.** A friend should be able to try Overwatch in
  under 30 seconds. No email verification flows, no password reset
  forms.
- **Mobile-friendly.** PWA on iOS Safari + Chrome on Android must both
  work. The session must survive PWA install (standalone mode).
- **Cheap.** No new infra (no Redis, no Auth0 free-tier quota worry).
- **Reuses what we already have.** We already integrate Google Calendar
  via OAuth2. If we use Google for auth too, users are already
  authorizing us anyway.

## Decision

**Google OAuth 2.0 as the only sign-in method, with JWT session
cookies set as httpOnly + SameSite=Lax.**

### Auth flow

```
Browser                         Backend                       Google
   │                               │                            │
   │ ── GET /auth/google/login ──▶ │                            │
   │                               │ ── redirect URL ─────────▶ │
   │ ◀──────── 302 to Google ──────│                            │
   │                                                            │
   │ ── (user signs in at Google) ─────────────────────────────▶│
   │                                                            │
   │ ◀── 302 to /auth/google/callback?code=... ──────────────── │
   │                               │                            │
   │ ── GET /auth/google/callback?code=... ─▶                   │
   │                               │ ── POST /token ──────────▶ │
   │                               │ ◀── {id_token, ...} ────── │
   │                               │                            │
   │                               │ (verify id_token, find or
   │                               │  create user row, mint JWT)
   │                               │                            │
   │ ◀── 302 to / + Set-Cookie: ow_session=<JWT> ──             │
```

### Session storage

- **JWT signed with HS256** using `SESSION_SECRET` (env var, 32+ chars)
- **30-day expiry**, refreshed on each `/auth/me` call within 7 days
  of expiry
- **httpOnly cookie** — inaccessible to JavaScript, immune to XSS
  token theft
- **SameSite=Lax** — sent on top-level navigations (so OAuth callback
  redirects work) but not on third-party XHR (CSRF protection)
- **Secure flag** in production (cookie only sent over HTTPS)

### Endpoints

| Endpoint | Auth | Purpose |
|---|---|---|
| `GET /auth/google/login` | none | Returns Google's OAuth URL or redirects to it |
| `GET /auth/google/callback` | none | Receives code, exchanges for token, sets cookie |
| `GET /auth/me` | required | Returns `{id, email, name}` or 401 |
| `POST /auth/logout` | required | Clears the session cookie |

### Protected routes

A FastAPI dependency `current_user(request)` reads the cookie, verifies
the JWT, looks up the user in the database, and either returns the
user object or raises `HTTPException(401)`. Every protected route
takes `user: User = Depends(current_user)`. The dependency is the
single chokepoint — no route can accidentally skip auth.

Public routes (unauthenticated): `/auth/*`, `/health`, and
`/push/vapid-public-key` (the public key is, well, public).

### Frontend

- A new `AuthContext` provides `{user, loading, login, logout}` to the
  tree
- On mount, fetch `/auth/me`. If 401, render `<LoginScreen>`. If 200,
  render the app.
- `<LoginScreen>` is a single button: "Sign in with Google" that
  navigates to `/auth/google/login`
- After the callback redirects back to `/`, the cookie is set and the
  next `/auth/me` succeeds

## Alternatives considered

### Email + password

Classic web auth: signup form, bcrypt hashes, email verification, password
reset.

**Rejected because:**
- ~10x more code to write and test correctly (verification email
  delivery, password reset tokens, rate limiting on login attempts)
- Adds infra: needs an email provider (SendGrid, Resend) for verification
- Higher signup friction — friends will bounce off the form
- We already have Google integration for Calendar — making users
  authorize twice (once for auth, once for calendar) is worse than once
- All my target users have Google accounts

### Magic links (passwordless email)

Email a one-time link to log in. No password.

**Rejected because:**
- Still needs an email provider
- Worse mobile UX (switch to email app, click link, switch back)
- Tokens delivered via email are fragile in spam filters

### Auth0 / Clerk / Supabase Auth

Drop in a third-party auth service.

**Rejected because:**
- Free tiers have user caps (Auth0: 7k MAU, Clerk: 10k) — fine, but
  feels like over-engineering for a 5-friend launch
- Adds a vendor dependency for something we can build correctly in a
  few hours
- The "learning value" of building auth ourselves is meaningful for
  Tanmay's portfolio
- Easy to migrate to one later if we outgrow the hand-rolled version

### Session storage in a server-side table (DB-backed sessions)

Each session = a row keyed by random session ID. Cookie stores the ID.

**Rejected because:**
- One extra DB query per authenticated request (every endpoint hits the
  sessions table to validate)
- JWTs are stateless — no DB lookup needed for validation
- Revocation is genuinely harder with JWTs (no "delete session" — you
  have to wait for expiry or maintain a denylist). We accept this for
  now; logout just clears the cookie, and the 30-day exposure window
  is acceptable for our threat model.

### Token in localStorage instead of httpOnly cookie

Send `Authorization: Bearer <JWT>` header on every request.

**Rejected because:**
- localStorage is readable by any script — one XSS vulnerability
  exfiltrates every user's session
- httpOnly cookies are the OWASP-recommended default
- The CSRF risk is mitigated by SameSite=Lax + only allowing same-site
  POST/PATCH/DELETE

## Consequences

### Positive

- **30-second signup.** Click "Sign in with Google," see Google's
  consent screen, you're in.
- **Already-authorized for Calendar.** When a user later opts in to
  Calendar sync, we reuse the OAuth grant (incremental scope request)
  rather than running OAuth twice.
- **No password infra.** No hashing, no reset flows, no email provider,
  no compromised-password lists.
- **Stateless auth.** JWT means we can horizontally scale the backend
  without sharing session state across instances. (Not relevant
  today but future-proofed.)
- **Cookie is HTTP-level.** Service worker push events authenticate
  the user correctly because the cookie travels with the
  fetch-from-service-worker call.

### Negative

- **Google-only.** A user without a Google account can't sign in. For
  our scope (friends), this is fine. Could add Apple later for free
  via the same OAuth pattern.
- **JWT revocation is best-effort.** If a session token is stolen,
  the attacker has up to 30 days. We can't "kick" the session before
  expiry without adding a denylist. Mitigations: short refresh
  windows, httpOnly cookie (much harder to steal than localStorage).
- **OAuth callback URLs are environment-specific.** Local dev,
  staging, and prod each need their own redirect URI registered in
  the GCP console. Documented in DEPLOYMENT.md.
- **No anonymous use.** Users must log in. The chat-first UX requires
  identity. (For a public demo mode, we'd need a "guest" path — out of
  scope.)

### Future considerations

- **Apple Sign In** (15 min of work — same OAuth pattern, different
  provider)
- **Refresh tokens for longer sessions** without sacrificing security
  (rotation pattern)
- **2FA** if we ever store sensitive data (we don't today)
- **Account deletion endpoint** + cascade delete of user's data
  (required for GDPR if we ever go public — currently noted as a
  Slice 14+ todo)
- **Audit log** of who logged in when (compliance, not needed for
  friends-only launch)

## References

- [Google OAuth 2.0 docs](https://developers.google.com/identity/protocols/oauth2)
- [OWASP — JSON Web Token Cheatsheet](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html)
- [OWASP — Session Management Cheatsheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- ADR-0010 — multi-tenancy (scoping data by user_id; the next slice)
- ADR-0011 — production deployment (the slice that takes this live)
