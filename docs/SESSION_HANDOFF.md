# Session Handoff — 2026-06-07

Quick-resume notes so the next session (or future-you) can pick up fast.
The app is **live and in real daily use**:

- Frontend: https://overwatch-ai-seven.vercel.app
- Backend:  https://overwatch-ai-production.up.railway.app
- Repo: github.com/Tanmay-Hatkar/overwatch-ai (branch `main`)
- Mode: single-user private deploy (ALLOWED_GOOGLE_EMAILS = tanmay.hats@gmail.com)

## Shipped this session (all on main, deployed)

| Commit | What |
|---|---|
| `db56ce6` | **Timezone fix** — device sends IANA tz; backend resolves "now" in user's zone, injects local time into chat prompt, stores due_at as UTC. Fixes "in 30 min", "tonight at 7", date-line drift, and reminders firing at the wrong absolute time. +3 tests (197 total). |
| `8d0964d` | **ChatBar overlap** — ResizeObserver reports bar height; page pads bottom dynamically so content is never hidden behind the fixed chat on phones. |
| `851b434` | **UX polish** — friendlier briefing error + "try again" button; "Enable push reminders" is now a pill button with bell icon; gentle page fade-in (respects reduced-motion). |
| earlier | Empty calendar provider in prod, commitment markers visible on grid, "add to calendar"=add_commitment, time/date questions allowed, 70vw width, removed mock-only sections. |

## Open items (priority order)

### 🔴 Blocking real use
1. **VAPID_PUBLIC_KEY on Railway is WRONG** — currently holds the 27-char
   `mailto:...` value instead of the ~87-char public key. Push reminders
   won't work until fixed. The user needs to re-paste the correct
   `VAPID_PUBLIC_KEY` (and verify `VAPID_PRIVATE_KEY` ~43 chars) from
   local `backend/.env` into Railway Variables. Verify with:
   `curl https://overwatch-ai-production.up.railway.app/push/vapid-public-key`
   — public_key should be ~87 chars, base64url, decodes to 65 bytes.

### 🟡 Next slice — biggest value
2. **Slice 12 — Multi-tenancy + per-user Google Calendar OAuth**
   (paused on branch `feature/slice-12-multi-tenancy`, ~50% done).
   See `docs/SLICE_12_PROGRESS.md` for the full checklist + pattern.
   This is what makes the empty calendar show REAL events and lets
   friends sign in. Remaining: calendar/push/stats/chat services scoped
   by user_id, GoogleTokensRepository, per-user OAuth routes, conftest +
   test sweep. NOTE: main has since diverged (timezone fix etc.), so the
   branch will need a rebase/re-apply rather than a clean merge — easier
   to re-apply the slice-12 pattern fresh onto current main using the
   progress doc than to merge the stale branch.

3. **Slice 14 — Voice in/out** (Web Speech API) — the user's dream
   feature. Long-press chat bar to speak; spoken briefings. ~1-2 days.

### 🟢 Polish backlog (non-blocking)
- Multi-commitment add: "A, B, C" should add all (currently adds first +
  invites rest as separate messages).
- Calendar auto-collapse empty late hours; "now" line indicator.
- Settings panel currently near-empty — add notification prefs, calendar
  connect button (after slice 12), sign-out, data export.
- Push reminder quick-actions (✓ Done / ⏰ Snooze from the notification).
- Reminder escalation if unacknowledged.
- Streak/stats surfaced on home (StatsBar component still exists, unused).

## Feature wishlist (from user-perspective, on-mission)
Capture: voice, share-to-Overwatch intent, bulk add, photo→OCR.
Triage: auto-categorize work/personal/health, defer-to-weekend, swipe-complete.
Engage: push quick-actions, weekly review email, escalating reminders.
Confidence: completion history, "yesterday you did 4/6".
Integrations: email parse ("I'll send by Friday"), Slack, real calendar.
Conversational: long-term memory, TTS replies, configurable personality.
(Stay OFF: notes, project mgmt, team collab, pomodoro, generic AI chat.)

## How to resume
1. Fix the VAPID key (user, 1 min) — unblocks push.
2. Then either: (a) finish Slice 12 (multi-tenancy + real calendar) using
   SLICE_12_PROGRESS.md, or (b) Slice 14 (voice) for the wow factor.
3. Run `cd backend && python -m pytest -q` — expect 197 passing.
4. Frontend: `cd frontend && npm run build` — expect clean.

## Key facts to remember
- Tests: 197 passing. Backend deps include tzdata now.
- Both Railway + Vercel auto-deploy on push to main.
- Calendar shows EMPTY in prod (EmptyCalendarProvider), MOCK in dev.
- Cookies are SameSite=None in production (cross-domain SPA→API).
- The chat `/chat` endpoint now accepts an optional `timezone` field.
