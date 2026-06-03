# 0007: Web Push notifications via VAPID + background reminder scheduler

- **Status:** Accepted
- **Date:** 2026-06-02
- **Deciders:** Tanmay Hatkar

## Context

ADR 0005 documented in-tab browser notifications — useful, but they
only fire when an Overwatch browser tab is open. The PRD's "surgical
follow-up" mechanic is significantly weaker if the user has to keep
the app open all day to receive reminders.

To deliver reminders when the tab is closed (or the browser is
backgrounded), the only viable web technology is **Web Push** with
VAPID-signed payloads. The flow:

1. The Service Worker registers a push subscription with the browser's
   push service (FCM, APNs, Mozilla's autopush, etc.)
2. The frontend sends that subscription to our backend
3. When something needs to fire, our backend sends a payload through
   the push service, signed with our VAPID private key
4. The browser wakes the service worker, even with no tabs open
5. The SW's `push` event handler calls `showNotification()`

This requires several pieces:

- A persistent identity for the app (VAPID keypair)
- Backend storage for subscriptions
- A backend process that monitors commitments and decides when to push
- A frontend flow to opt in
- A service worker capable of handling the push event

## Decision

**Implement Web Push end-to-end with an in-process background
scheduler.**

### Architecture

```
┌─────────────────────────────────────┐
│ Browser (Overwatch tab + SW)         │
│   PushSetup.jsx ──► enablePush()     │
│        │                              │
│        ▼ POST /push/subscribe        │
└────────┼────────────────────────────┘
         │ subscription (endpoint, keys)
         ▼
┌─────────────────────────────────────┐
│ Backend (FastAPI process)           │
│   PushSubscriptionRepository (SQLite)│
│   PushService.broadcast(...)        │
│        ▲                            │
│        │ called from               │
│   ReminderScheduler._tick()        │
│        ▲                            │
│        │ runs every 60s            │
│   (asyncio task started in lifespan)│
└─────────────────────────────────────┘
         │ webpush(VAPID-signed payload)
         ▼
   Browser's push service (Google/Mozilla/Apple)
         │
         ▼
   Browser wakes the Service Worker
         │
         ▼
   sw.js push handler → showNotification()
```

### Key choices within that architecture

- **VAPID keypair stored in `.env`.** Public key is exposed via
  `GET /push/vapid-public-key` (frontend needs it for `subscribe()`).
  Private key signs payloads server-side; never leaves the backend.

- **Subscriptions stored in SQLite** as `push_subscriptions(id,
  endpoint, p256dh, auth, created_at)`. Endpoint is unique — a
  re-subscribe from the same browser upserts rather than duplicating.

- **In-process scheduler via `asyncio` + FastAPI lifespan.** Spawned
  on app startup, stopped cleanly on shutdown. Each tick runs the sync
  database queries in a worker thread (`run_in_executor`).

- **In-memory "notified IDs" set.** Prevents re-pushing for the same
  commitment within a process lifetime. First tick after startup
  silently marks all already-overdue items (same first-check
  suppression as the in-tab hook in ADR 0005).

- **`pywebpush` for VAPID signing + delivery.** Handles the JWT
  signing, payload encryption, and HTTP delivery. We wrap it to
  recognize 404/410 responses (stale subscriptions to be pruned).

- **A `POST /push/test` route.** Manually broadcasts a test payload
  to all subscriptions. Critical for debugging the pipeline without
  waiting for a real commitment to become overdue.

## Alternatives considered

### Defer push entirely; stay with in-tab notifications only

Push adds significant complexity (VAPID, service worker, backend
scheduler). We could just live with in-tab reminders.

**Rejected because:**
- The "surgical follow-up" mechanic is the differentiating feature
  per the PRD; weakening it weakens the whole product
- Once the user installs the PWA on a phone, push is the ONLY
  channel that reaches them (no concept of "tab open")
- The complexity is real but contained — one new feature area, one
  ADR, ~500 lines of code total

### Polling from the service worker (no backend scheduler)

The service worker could run periodic background sync, fetch
commitments, and decide to notify on its own.

**Rejected because:**
- `BackgroundSync` and `PeriodicBackgroundSync` have limited browser
  support and aggressive throttling
- Forces the SW to know about commitment semantics (overdue, status,
  due_at) — duplicates logic that lives on the backend
- Sync intervals are heavily browser-controlled (often hours), too slow
  for time-sensitive reminders
- Battery-bad — the device must wake up to poll

### Use a managed push service (Pusher, OneSignal, Knock)

Outsource the push delivery + VAPID handling.

**Rejected because:**
- Adds an external dependency and a new vendor account
- Adds cost (free tiers run out quickly)
- VAPID + pywebpush is genuinely simple at our scale
- Owning the keys means we can switch transports later without
  re-asking users to subscribe

### Persistent "last notified at" column on commitments

Instead of an in-memory set, record per-commitment when it was last
pushed.

**Rejected for now because:**
- Requires a migration; defer until we hit the actual problem (a
  user restarts and gets a notification storm)
- In-process set handles the common case — the user doesn't restart
  the backend more than once a day
- Migration becomes trivial once we have Alembic set up (future
  hosted-backend slice)

### APScheduler instead of raw asyncio

Use a proper scheduler library with cron-like syntax.

**Rejected because:**
- Adds a dependency for one use case
- Our needs are "tick every N seconds" — asyncio + sleep is sufficient
- APScheduler shines when you have many heterogeneous jobs; we have one

## Consequences

### Positive

- **Reminders reach the user off-tab.** This is the headline feature.
- **Works across phone PWA installations.** When the user installs
  Overwatch on Android via the existing manifest, push notifications
  arrive natively just like a real app.
- **Stale subscriptions self-prune.** 410-Gone responses are detected
  and the subscription is deleted, so the database doesn't accumulate
  dead endpoints.
- **Backend-owned trigger logic.** Push decisions happen server-side
  with full database visibility. Easy to extend (e.g., "remind 15 min
  BEFORE due_at") without touching the SW.
- **Defensive errors throughout.** Any push failure logs + continues
  to the next subscription. One bad endpoint doesn't block others.
- **Foundation for multi-device.** When the user adds a phone PWA,
  it just creates another subscription row; pushes broadcast to
  everything.

### Negative

- **State lost on restart.** The in-memory notified set means
  currently-overdue items will be silently re-marked on the first
  tick after a backend restart, but if a user restarts mid-day and
  the same commitment hadn't already been pushed, they may now miss
  it. Acceptable for single-user MVP.
- **Single-instance assumption.** The in-process scheduler doesn't
  coordinate across replicas. When/if we host on multiple servers,
  we'll need a leader-election mechanism or move to a job queue
  (Redis + RQ, Celery, etc.).
- **VAPID claims expire in 24h.** `pywebpush` handles this
  transparently, but if we ever switch transports we'd need to
  re-implement the JWT signing flow.
- **iOS Safari push is partial.** iOS 16.4+ supports Web Push for
  installed PWAs only. Users browsing in Safari won't get pushes
  until they "Add to Home Screen" — a real UX friction point.
- **Browser-side debugging is hard.** Service worker errors don't
  surface in normal DevTools tabs by default. We added clear
  logging and a `/push/test` endpoint to make this less painful.

### Future considerations

- **`completed_at` migration** + persistent "last notified at"
  column → survives restart, deduplicates across replicas
- **Snooze:** a notification action button that calls
  `POST /commitments/{id}/snooze` (pushes back due_at by 10/30/60 min)
- **Smart timing:** instead of firing exactly at due_at, fire
  N minutes before based on commitment text (e.g., 15 min before
  a meeting, day-of for a deadline)
- **Push for briefings:** morning briefing arrives as a push at
  the user's chosen wake time
- **iOS-specific UX:** detect Safari-without-PWA and explicitly
  prompt to install for reliable push

## References

- ADR-0005 (in-tab browser reminders) — the prior step, now
  complemented by this
- Web Push specification: https://datatracker.ietf.org/doc/rfc8030/
- VAPID specification: https://datatracker.ietf.org/doc/rfc8292/
- `pywebpush`: https://github.com/web-push-libs/pywebpush
- `backend/app/services/push_service.py` — the wrapper around webpush
- `backend/app/services/reminder_scheduler.py` — the polling loop
- `backend/app/routes/push.py` — subscribe / unsubscribe / test routes
- `frontend/src/lib/push.js` — subscription helpers
- `frontend/src/components/PushSetup.jsx` — the opt-in UI
- `frontend/public/sw.js` — push event handler
