# 0020: Home-screen widget (Jetpack Glance + WorkManager pull)

- **Status:** Accepted
- **Date:** 2026-07-09
- **Deciders:** Tanmay Hatkar

## Context

The founder asked for a "lock screen interface" — a way to see upcoming
commitments without unlocking the phone.

**Framing correction, made explicit here because it changes what gets
built:** true per-app lock-screen widgets were removed from Android in
5.0 Lollipop (2014) and have not existed as a distinct platform surface
since. As of Android 16 QPR2 (Dec 2025), a lock-screen widget *area* has
returned, but only on supporting Pixel devices, and it works by pinning
the **same `AppWidgetProvider`/Glance mechanism** used for ordinary
home-screen widgets — any home-screen widget "just works" there
automatically unless the widget explicitly opts out. Samsung has a
separate, OEM-specific mechanism (Good Lock's "LockStar" module) that
similarly just pins an app's existing home-screen widget to its own lock
screen; it is not a distinct API either.

**There is no separate "lock screen widget" API to build against.** So
this ADR describes building exactly one thing: a standard Android
home-screen widget. Where the underlying OS/OEM supports lock-screen
placement, the user gets that placement option for free, with zero
additional code. Where it doesn't (most Android versions/OEMs today),
the founder still gets the home-screen widget, which is the vast majority
of the value of "glanceable commitments without opening the app."

## Decision

Build **one Jetpack Glance home-screen widget** (`CommitmentWidget`)
showing the 3 nearest-due open commitments, refreshed by a **WorkManager
periodic pull every 30 minutes**, reusing the **same
`@capacitor/preferences` SharedPreferences token storage** the rest of the
native app already uses for auth — no new auth mechanism.

### Widget technology: Jetpack Glance

Glance (`androidx.glance:glance-appwidget`) is Google's current,
actively-developed widget toolkit — it compiles a subset of Jetpack
Compose down to `RemoteViews` under the hood, so the UI is declarative
Kotlin instead of hand-assembled `RemoteViews` calls. It is the option
Google is investing in going forward.

### Freshness strategy: WorkManager 30-minute periodic pull

A `PeriodicWorkRequest`, constrained to `NetworkType.CONNECTED`, fetches
`GET /commitments?status_filter=open` and writes the 3 nearest-by-`due_at`
items into each widget instance's Glance state
(`PreferencesGlanceStateDefinition`). 30 minutes is not an arbitrary
choice — it is the practical floor for *both*
`AppWidgetManager.updatePeriodMillis` and `PeriodicWorkRequest`; Android
silently clamps shorter intervals up to it regardless of what's
requested, so there is no meaningfully fresher pull-based option
available.

### Token reuse: the same SharedPreferences file `native.js` already writes

The native app's Google sign-in flow (`frontend/src/lib/native.js`,
`@capacitor/preferences`) already stores the bearer session token in the
device's local storage. `@capacitor/preferences` on Android is a thin
wrapper over a plain, app-private `SharedPreferences` file — by default
named `CapacitorStorage` (confirmed by reading
`PreferencesConfiguration.DEFAULTS.group` in the plugin's Android
source), storing the raw key/value pair `ow.session.token` → `<jwt>` with
no additional wrapping. `CommitmentWidgetRepository` reads that exact
file and key directly. This means the widget authenticates with zero new
auth code — it rides on whatever session the app itself is signed into
— at the cost of a hidden coupling: if either side (the JS token-storage
code or the widget's Kotlin read) changes independently, the widget's
auth silently breaks. Flagged here so a future change to `TOKEN_KEY` or
the Preferences `group` gets grepped for widget usage before shipping.

### Deep link reuse: the existing `overwatch://` custom scheme

Row taps deep-link via `overwatch://commitment/{id}` — the same custom
URL scheme already registered in `AndroidManifest.xml` and used by the
OAuth callback (`overwatch://auth?token=...`, see `backend/app/routes/auth.py`
`_NATIVE_REDIRECT_SCHEME`). A second `<intent-filter>` with
`android:host="commitment"` was added to `MainActivity` rather than
inventing a second deep-link mechanism. v1 only wires the *platform*
routing (tapping a row opens the app on this route); making the SPA
actually navigate to that specific commitment on receiving this deep link
is a small frontend follow-up, out of scope here.

### Accepted v1 gap: no bearer-token refresh

Reading `backend/app/routes/auth.py` confirms native bearer tokens have no
refresh endpoint — `GET /auth/me` refreshes the **cookie** for web
callers (`should_refresh(session)`), but explicitly skips this for bearer
callers: *"bearer callers (native) carry the token themselves and re-auth
via /auth/google/login."* Tokens are minted with `session_max_age_days`
and simply expire; the native app's only recovery path today is a full
interactive re-sign-in. Building a refresh endpoint is out of scope for
this slice. The widget's contract with that gap: on a 401, render "Tap to
re-sign in." cleanly (tapping opens `MainActivity`, which drives the same
sign-in flow the app already has) rather than crashing or silently
showing stale data forever.

## Alternatives considered

- **Hand-rolled `RemoteViews` (no Glance):** more boilerplate, more manual
  `PendingIntent`/layout-XML wiring, and it's the legacy approach Google
  is steering developers away from. Rejected — Glance is free (part of
  Jetpack, no license cost) and actively maintained.
- **Push-triggered refresh (FCM):** would keep the widget fresher than 30
  minutes by having the backend push a "your data changed" signal. Real,
  legitimate future work — but it requires standing up a *second*,
  native-only push channel (Firebase Cloud Messaging) alongside the
  existing browser-only Web Push/VAPID system (ADR-0007), which is a
  meaningfully bigger slice than a widget. Deferred, not rejected.
- **Cache-only (no periodic refresh, only updates when the app is
  opened):** simplest possible implementation, but defeats the widget's
  entire purpose — "glanceable without opening the app" requires the data
  to update *without* the app being opened. Rejected as insufficiently
  fresh.
- **A distinct "lock screen widget" build:** rejected outright — per the
  Context section above, this isn't a real, separate thing to build on
  current Android. Building "one more" widget variant for the lock screen
  would be pure wasted effort.

## Consequences

### Positive

- Founder gets a real, working home-screen widget showing their nearest
  commitments without opening the app — and gets lock-screen placement
  "for free" on any device/OEM that supports it, no extra code.
- Zero new auth surface — reuses the exact token the app already
  maintains.
- Zero new deep-link mechanism — extends the existing `overwatch://`
  scheme.
- Offline-tolerant by construction: Glance state always holds
  last-known-good data; a failed fetch (offline, backend down) leaves the
  widget showing what it last successfully knew, with a stale-data badge,
  rather than going blank or crashing.

### Negative

- **Up to 30 minutes stale**, always — this is a pull, not a push. A
  commitment added or completed in the app can take up to half an hour to
  show/clear on the widget.
- **No refresh token.** After ~30 days of no sign-in, the widget silently
  degrades to "Tap to re-sign in." with no automatic recovery — an
  accepted v1 gap, not a bug.
- **Hidden coupling to `@capacitor/preferences`'s storage format.** If a
  future Capacitor major version changes how/where `Preferences` stores
  data on Android, or `native.js`'s `TOKEN_KEY`/group changes, the widget
  breaks silently (renders "Tap to re-sign in." even though the user *is*
  signed in) until someone notices and updates the widget's read path to
  match.
- **First Kotlin file in `frontend/android/`.** Adds Kotlin-Android-plugin
  + Compose-compiler Gradle plumbing to a previously Java-only module —
  slightly more build surface area (see the Gradle changes listed in the
  implementation PR/commit) for future maintainers to understand.
- **Not testable in this environment.** No instrumentation/Robolectric
  coverage was added — the sandbox this was built in has no working
  Java/Android SDK/Gradle toolchain to run tests against. See the manual
  verification checklist in the implementation commit for what a human
  with real Android Studio needs to check before this ships.

### Future considerations

- FCM push-triggered refresh, to close the up-to-30-minutes staleness gap
  (would sit alongside, not replace, the WorkManager pull as a safety
  net).
- A native bearer-token refresh endpoint, to close the no-refresh v1 gap.
- Frontend routing so `overwatch://commitment/{id}` actually navigates to
  that commitment instead of just opening the app.
- A widget configuration screen (e.g. choose which group/section to
  show), if the flat "3 nearest-due" view turns out to be too coarse.

## References

- ADR-0007 — Web Push notifications (the existing, browser-only push
  system the FCM alternative would have had to duplicate)
- ADR-0009 — Google OAuth authentication (bearer-token native auth flow)
- `frontend/src/lib/native.js` — `TOKEN_KEY`, `@capacitor/preferences` usage
- `backend/app/routes/auth.py` — bearer-token contract, no-refresh confirmation
- `backend/app/routes/commitments.py` — `GET /commitments?status_filter=open`
- `frontend/android/app/src/main/java/com/tanmayhatkar/overwatch/widget/` — implementation
- [Jetpack Glance docs](https://developer.android.com/develop/ui/compose/glance)
- [WorkManager periodic work docs](https://developer.android.com/develop/background-work/background-tasks/persistent/how-to/define-work#kotlin_1)
