# The Build Log — The Making of Overwatch

> The narrative companion to the ADRs. The ADRs say *what* we decided and
> list the alternatives formally. This document tells the *story* — the
> origin, the methodology, the blockers, the forks in the road, and why
> we walked the paths we did. Read it start to finish and you'll
> understand not just how Overwatch is built, but how it came to be.

**Last updated:** 2026-06-08

---

## Chapter 1 — Origin: why there's a v2 at all

Overwatch started life as **ARIA**, then was renamed. The first real build —
call it **v1** — grew fast and messy. By **2026-04-30** it was paused. Not
because the idea was wrong, but because the *execution* had rotted:

- Too many half-finished features, none fully done
- No GitHub repo — the code lived only on one machine
- No CI, no tests gating changes
- No record of *why* anything was built the way it was

v1 had reached the state every solo project fears: too tangled to safely
change, too undocumented to confidently resume. The lesson wasn't "the
idea failed." It was "**velocity without discipline produces a codebase
you're afraid of.**"

So v2 was a deliberate reset — same product vision, opposite methodology.
New home: `github.com/Tanmay-Hatkar/overwatch-ai`. New rule: **nothing
ships half-done, and every non-obvious decision gets written down.**

The product vision never changed, and it's worth stating because it drives
every later decision:

> Plans don't die from being unmade. They die from being *forgotten*.
> Overwatch is a memory layer over the commitments you make to yourself —
> capture them in natural language, resurface them at exactly the right
> moment.

Not a to-do app. Not a calendar. A re-engagement engine.

---

## Chapter 2 — The Method: the discipline that saved v2

Three rules shaped everything, and they're the reason v2 didn't rot like v1.

### Vertical slices (ADR-0001)
Every feature ships **end to end** — UI + API + database + tests — before
the next one starts. No "build all the backend, then all the frontend."
Each slice is independently demoable and independently safe. If you stop
after any slice, what exists *works*.

### Architectural Decision Records (ADRs)
Every meaningful decision gets a numbered markdown file: the context, the
decision, the **alternatives considered and why they were rejected**, and
the consequences. This is the antidote to v1's "why is this like this?
nobody knows." Eleven ADRs exist as of this writing (0001–0011).

### The 8 non-negotiable code rules
Type hints everywhere. Docstrings everywhere. try/except on every external
call. Logging, never print. A unit test for every function with external
deps mocked. Single responsibility. No hardcoded values (everything in
config). Secrets in `.env`, never committed.

These aren't bureaucracy — they're the specific habits whose *absence*
killed v1. The test suite (205 tests by the time we deployed) is the
enforcement mechanism: you can't merge something that breaks the contract.

---

## Chapter 3 — The Build, slice by slice

Each slice taught something. Here's the arc.

| # | Slice | What shipped | The lesson |
|---|---|---|---|
| 1 | Commitment CRUD | The core entity + REST routes + repository pattern | Get the layering right early; everything else rides on it |
| 2 | LLM fallback chain | `call_llm()` orchestrator: OpenAI → Groq → Ollama | Never depend on one provider; resilience is a design choice (ADR-0002) |
| 3 | NL commitment parser | "call mom tomorrow 3pm" → structured commitment | Prompt engineering for structured output: date tables, temp=0, defensive JSON (ADR-0003) |
| 4 | Reminder scheduler | Background async task polling for due commitments | Polling beats cron for a single-process app (ADR-0004) |
| 5 | Morning briefing + cache | LLM-generated daily summary, cached with invalidation | Don't re-call the LLM when nothing changed (ADR-0005) |
| 6 | Stats | Completion counts, streak, 7-day series | — |
| 7a | Calendar provider abstraction | `CalendarProvider` base + Mock impl | Abstract the external dependency so you can swap/fake it (ADR-0006) |
| 7b | Google Calendar (real) | Live Google Calendar via OAuth | Reused the existing GCP project's token |
| 8 | Web Push | VAPID keys, service worker push event | Notifications that fire even when the tab is closed (ADR-0007) |
| 9 | Weekly calendar UI | The 7-day hero grid + briefing card | — |
| 10 | Conversational chat | Single LLM call: classify intent + reply | The novel mechanic, finally conversational (ADR-0008) |
| 11 | Auth foundation | Google OAuth login + JWT sessions | The gateway to multi-user (ADR-0009) |

By slice 11, Overwatch was a real, tested, multi-feature AI product —
running only on localhost. The next act was getting it onto the internet.

---

## Chapter 4 — The Deployment Saga (the war stories)

This is the part no tutorial prepares you for. The code was done and
tested; getting it *live* surfaced a string of blockers, each of which
taught a real lesson. In order:

### Blocker 1 — Railway built the wrong thing
Railway autodetected the repo but tried to build from the root. Overwatch's
backend lives in `backend/`. **Fix:** set the service Root Directory to
`backend`. *Lesson: monorepos need the platform told where the app is.*

### Blocker 2 — The persistent volume
SQLite lives in a file. Containers have ephemeral filesystems — every
redeploy would wipe the database. **Fix:** a Railway volume mounted at
`/data`, plus a `DATABASE_PATH` env var so the app writes there. *Lesson:
"where does my data physically live" is a question you must answer before
deploy, not after.*

### Blocker 3 — CORS
The frontend (Vercel, `*.vercel.app`) and backend (Railway,
`*.railway.app`) are **different origins**. The browser blocked every API
call. **Fix:** FastAPI CORS middleware with the exact Vercel origin in
`CORS_ORIGINS` (no wildcard, because we send credentials). *Lesson: split
frontend/backend hosting = CORS is not optional, it's day one.*

### Blocker 4 — The env vars that "wouldn't take"
CORS *still* failed after setting the var. The deployed container was
running with the old environment — Railway hadn't picked up the change,
and several required vars (GROQ_API_KEY, DATABASE_PATH, the VAPID keys)
were missing entirely. **Fix:** a full, correct env block + a forced
redeploy. *Lesson: env changes need a deploy to take effect, and a missing
var fails silently into a default.*

### Blocker 5 — SameSite cookies (the subtle one)
Login *succeeded* — Google authorized, the backend set a session cookie —
but the app still showed the login screen. The cause: the session cookie
was `SameSite=Lax`, and the browser refuses to send a Lax cookie on
cross-site XHR (vercel.app → railway.app). So `/auth/me` always looked
logged-out. **Fix:** `SameSite=None; Secure` in production (Lax stays in
dev, where everything is localhost). *Lesson: cross-domain SPA + cookie
auth has a specific, non-obvious cookie requirement.*

### Blocker 6 — The Google "Desktop vs Web" client trap
The "Connect Google Calendar" redirect URIs were nowhere to be found in
the GCP console. Reason: the OAuth client was created as a **Desktop**
application type — which has no concept of authorized redirect URIs. The
hosted web flow needs a **Web application** client. **Fix:** create a new
Web OAuth client, update `GOOGLE_CLIENT_ID`/`SECRET` everywhere. *Lesson:
OAuth client *type* is not cosmetic — it determines which flows are even
possible.*

### Blocker 7 — The VAPID key that wouldn't update
The push public-key endpoint kept returning a 27-character value (the
`mailto:` subject) instead of the 87-character key. Re-pasting in Railway's
UI didn't take. **Fix in progress:** delete the variable entirely and
recreate it. *Lesson: when an edit-in-place won't stick, delete and
recreate.*

### Blocker 8 — The redirect URIs you deleted
Mid-setup, the login redirect URIs got removed from GCP while editing —
which would break sign-in for everyone. **Fix:** restored all four URIs
(login + calendar, prod + local). *Lesson: OAuth redirect URIs are
load-bearing; treat the list as production config.*

The throughline of the whole saga: **the code being correct is maybe half
the battle. The other half is the dozen environment, identity, and
cross-origin details that only surface when real browsers talk to real
servers across real domains.**

---

## Chapter 5 — The Forks (alternatives we genuinely weighed)

Good engineering is mostly choosing well between viable options. The real
forks:

### PWA vs React Native vs Capacitor (mobile)
The pull toward "a real mobile app" recurred several times. The honest
sequence we landed on: **ship the PWA first** (zero new code, on the phone
in hours) → *use it* to validate the habit is real → only then invest in
native. When native became justified (the desktop "feel" wasn't pulling
daily use, and voice is genuinely better native), we chose **Capacitor**
over a React Native rewrite: it wraps the *existing* React app in a native
shell (~90% reuse, days) rather than rebuilding the UI (~80% rewrite,
weeks). React Native stays the fallback if the webview feel ever proves
insufficient. *Principle: ship the cheap version, let real use decide the
expensive one.*

### SQLite vs Postgres vs Supabase (data)
v1-era thinking favored Supabase (Postgres + auth + storage in one box).
But by v2 we'd **built our own auth** — adopting Supabase would mean
throwing away working, tested code to take on vendor lock-in. Decision:
**stay on SQLite** now (fine for single-user + a few friends), move to
**Railway Postgres** (one click, same platform) when concurrent-write load
demands it — *not* Supabase. *Principle: the all-in-one box loses its
appeal once you've built the pieces yourself.*

### Tool calling vs prompt-engineered JSON (LLM actions)
Native function-calling APIs are the "modern" way to have an LLM trigger
actions. We chose **prompt-engineered JSON** instead — because native tool
calling is provider-specific and would break the OpenAI→Groq→Ollama
fallback chain (ADR-0008). *Principle: the textbook approach isn't free if
it costs you portability you care about.*

### RAG — considered and rejected
RAG (embeddings + vector DB + retrieval) is the default for "ground the
LLM in my data." We **don't use it**, deliberately: our knowledge is
*structured* (commitments in SQL rows), so plain SQL retrieval +
context-injection grounds the model without embeddings or a vector store.
*Principle: RAG is for unstructured documents; don't pay its complexity for
structured data.*

### Cookie vs bearer-token auth (the current fork)
Web login uses an httpOnly **session cookie**. But Google blocks OAuth
inside embedded webviews, and cookies are awkward across the native
webview boundary — so the Capacitor app needs a **bearer-token** path
(native sign-in → backend verifies → app stores a token → sends it as a
header). The app will detect its environment and pick the right one.
*Principle: native and web have genuinely different auth ergonomics; one
size doesn't fit both.*

---

## Chapter 6 — Where it stands, and what's next

**Live now:**
- Backend on Railway (FastAPI + SQLite on a volume), frontend on Vercel
- Google OAuth login working end to end (the SameSite saga resolved)
- Conversational chat, briefings, commitments, weekly calendar — all live
- Per-user Google Calendar connect (ADR-0011) — connect your real calendar
- 205 tests passing; auto-deploy on every push to main
- Private deploy, gated to one email whitelist

**In flight:**
- **Capacitor Android app** — wrapping the React app as a real Play Store
  app, with native auth + native voice (the current chapter being written)

**Deferred, on a branch:**
- **Multi-tenancy (slice 12)** — scoping every table by `user_id` so
  friends can sign in. Paused mid-refactor; resumable from
  `SLICE_12_PROGRESS.md`.

**Backlog:**
- VAPID push key fix (non-blocking)
- Voice in/out (native, the dream feature)
- Recurring commitments, snooze + push quick-actions, evening check-in,
  pattern learning ("you keep rescheduling this — drop it or commit?")

**The shape of the whole thing in one sentence:**
> A layered Python backend and a React frontend, where every external
> dependency lives behind a provider, every feature shipped as a vertical
> slice, every non-obvious decision has an ADR — built deliberately slowly
> so that, unlike v1, it never becomes a thing its author is afraid to
> change.

---

## Where to go deeper

- The formal decisions + alternatives: [docs/adr/](adr/) (0001–0011)
- The architecture map: [HANDBOOK.md](HANDBOOK.md)
- The deploy runbook: [DEPLOYMENT.md](DEPLOYMENT.md)
- The product vision: [PRD.md](PRD.md)
- The paused multi-user work: `SLICE_12_PROGRESS.md` (on the
  `feature/slice-12-multi-tenancy` branch)
