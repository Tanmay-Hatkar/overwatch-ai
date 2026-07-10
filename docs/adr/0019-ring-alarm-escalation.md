# 0019: Tier-2 ring-alarm escalation (full-screen intent, native Android)

- **Status:** Accepted
- **Date:** 2026-07-09
- **Deciders:** Tanmay Hatkar

## Context

`frontend/src/lib/notifications.js` already ships a native, on-device
reminder pipeline for the Android app: a `@capacitor/local-notifications`
alarm is scheduled per open commitment, reconciled in
`syncCommitmentReminders()` whenever commitments load, and offers
Snooze/Done actions right on the notification. Nothing in `docs/adr/`
documents this layer — ADR-0007 covers *server-side Web Push* for the
browser/PWA build, but the Android native-alarm system it sits alongside
has never had its own record. This ADR retroactively documents that
existing Tier-1 system, and formally records the new Tier-2 addition below.

That Tier-1 notification is, by Android design, an ordinary heads-up
notification: dismissible with one swipe, easy to glance at and ignore,
easy to lose in a shade full of other apps' notifications. For the PRD's
"surgical follow-up" mechanic — the whole point of Overwatch is
re-engagement, not just delivery — a notification that's trivially
swiped away without being acted on is a weak enforcement mechanism.

The founder (today, the app's only real user) asked for something closer
to "the phone actually rings" for commitments that get ignored: audible,
looping, full-screen, hard to dismiss by accident — the same UX class as
an alarm-clock app or an incoming phone call, not a typical push
notification.

Two concrete paths were on the table to deliver that:

- **Path A — full-screen-intent native alarm**, entirely within the
  already-installed Overwatch Android app: `AlarmManager` fires an
  exact alarm; on firing, a `NotificationCompat` full-screen intent
  launches a dedicated `Activity` that rings, vibrates, and shows the
  commitment with Snooze/Done.
- **Path B — a real PSTN phone call** placed to the founder's number via
  a telephony API (e.g. Twilio), so the phone literally rings as an
  incoming call, indistinguishable from any other call.

## Decision

**Implement Path A: native full-screen-intent ring escalation, as a new
"Tier 2" layered on top of the existing Tier-1 local-notification system.**

### Why Path A over Path B (real phone calls)

Path B is the more literal interpretation of "the phone rings," and nothing
here rules it out for later — but it was rejected for v1:

- **No genuinely free PSTN calling option exists.** Every viable provider
  (Twilio and equivalents) charges a recurring number rental (roughly
  $1/month) plus a small per-call rate (roughly $0.01–$0.02/minute).
  Trivial in absolute terms, but real recurring cost and a new billing
  dependency for a feature whose entire job is to save an
  already-installed app from being ignored.
- **Path A already achieves "hard to ignore" at $0 marginal cost.** The
  founder carries this exact phone, with this exact app installed, every
  day. A full-screen alarm that rings on the alarm audio stream, wakes
  the screen through the lock screen, and (where granted) bypasses Do Not
  Disturb gets extremely close to the phone-call experience without
  leaving the app or adding a vendor.
  - The gap that remains: Path A can be silenced by force-closing the app
    or by strict per-OEM battery management killing the alarm before it
    fires (see Consequences below). A real PSTN call doesn't have that
    failure mode. That gap is judged acceptable for v1.
- **Simplicity.** Path A is pure client-side Android code — no new
  backend service, no secrets to manage, no external account. Path B
  would need a backend trigger, a stored phone number, and telephony
  credentials, which is a materially bigger slice for a marginal
  reliability gain over Path A.

Path B remains a reasonable escalation-of-escalation for a future ADR if
Path A's failure modes turn out to matter in practice (e.g. if OEM battery
killing turns out to be a frequent, real problem).

### Architecture

```
Tier 1 (existing, retroactively documented here)
──────────────────────────────────────────────────
notifications.js: syncCommitmentReminders()
  → LocalNotifications.schedule() @ due_at − lead
  → fires as a normal heads-up notification (Snooze / Done actions)

Tier 2 (new)
──────────────────────────────────────────────────
notifications.js: syncCommitmentReminders()
  → ringAlarm.js: reconcileRingAlarms()
  → RingAlarmPlugin.ring({id, commitmentId, title, body, at})
  → AlarmManager.setAlarmClock(due_at + ESCALATE_AFTER_MINUTES)
       │ (fires even if the app process is dead)
       ▼
  RingAlarmReceiver (BroadcastReceiver)
       │ always posts a HIGH-importance notification with
       │ setFullScreenIntent(RingActivity, true)
       ▼
  RingActivity (full-screen, showWhenLocked + turnScreenOn)
       │ MediaPlayer loops the alarm-stream ringtone (USAGE_ALARM)
       │ + vibration, shows "Snooze" / "Done"
       ▼
  RingActionReceiver → persists action (SharedPreferences queue)
       │              → re-broadcasts locally
       ▼
  RingAlarmPlugin (if bridge alive) → notifyListeners('ringAction')
       ▼
  notifications.js: applyReminderAction() — the SAME handler Tier 1's
  Snooze/Done already uses (mark done via API / reschedule), which also
  cancels any still-pending sibling alarm on the other tier.
```

### Key choices within that architecture

- **`AlarmManager.setAlarmClock()` over `setExactAndAllowWhileIdle()`.**
  `setAlarmClock` is more Doze-resistant (the OS treats alarm-clock apps
  as a privileged, user-visible category) and shows a persistent
  status-bar alarm icon while armed — deliberate transparency: the user
  can always see "Overwatch has a ring pending" before it fires.

- **The notification is always posted with `setFullScreenIntent(...)`,
  with no manual branch for "permission not granted."** On Android 14+
  (API 34), if `USE_FULL_SCREEN_INTENT` is not granted, the OS itself
  downgrades this to a normal heads-up notification instead of launching
  the full-screen activity — this is documented platform behavior, so the
  app doesn't need to duplicate that check to get correct fallback
  behavior. The Snooze/Done actions attached directly to the notification
  (`RingAlarmReceiver`) are the usable fallback path in that case.

- **One shared JS action handler for both tiers.**
  `notifications.js`'s existing Snooze/Done handler was extracted into
  `applyReminderAction()` and is now invoked from both the Tier-1
  `localNotificationActionPerformed` listener and the new Tier-2
  `ringAction` listener (`ringAlarm.js`). Acting on either tier's UI does
  the same thing and — critically — cancels the sibling tier's still-armed
  alarm, so acknowledging a normal notification can never leave an
  orphaned full-screen ring waiting to go off later.

- **A persisted "pending ring actions" queue
  (`RingActionStore`, SharedPreferences).** If the alarm fires while the
  Capacitor bridge/app process isn't running, `RingActivity` still needs
  Snooze/Done to work. Those taps are queued natively and drained by
  `RingAlarmPlugin.drainPendingRingActions()` the next time
  `initNotificationActions()` runs (app open/resume) — not lost.

- **Own local reconciliation bookkeeping for Tier-2
  (`ringAlarm.js`'s `reconcileRingAlarms`).** Capacitor's
  `LocalNotifications.getPending()` gives Tier 1 a free "what's currently
  scheduled" list to diff against on every sync. `AlarmManager` has no
  equivalent introspection API reachable from a plugin, so Tier 2 tracks
  its own previously-scheduled id set in `localStorage` and cancels
  anything no longer in the new set — including clearing everything if
  the user turns the "Ring loudly" setting off.

- **Fixed `ESCALATE_AFTER_MINUTES = 10` constant (`ringAlarm.js`), not
  configurable in v1.** Simplest thing that works for a single user;
  revisit as a per-commitment or global setting if it needs tuning.

- **Ring-escalation setting defaults to ON.** Unlike most opt-in
  notification features, this one was explicitly requested by the app's
  only current user. Revisit the default once/if Overwatch has users who
  didn't ask for this behavior.

## Alternatives considered

- **Path B — real PSTN phone call (Twilio or similar):** described above.
  Rejected for v1 on cost/complexity grounds relative to the marginal
  reliability gain; Path A gets most of the value at zero incremental
  cost given the founder already carries this phone with this app
  installed. Worth revisiting if OEM battery-killing turns out to
  materially undermine Path A in practice.

- **`setExactAndAllowWhileIdle()` instead of `setAlarmClock()`:**
  rejected — no persistent status-bar affordance, and less Doze-resistant
  on aggressive OEM battery managers, for no upside over `setAlarmClock`
  in this use case.

- **A single combined Tier-1/Tier-2 alarm** (skip the heads-up step,
  always ring immediately): rejected — the PRD's model is "surgical,"
  not "alarming by default." A dismissible heads-up first, escalating
  only if ignored, matches how a considerate assistant (not a klaxon)
  should behave, and keeps the ring genuinely reserved for "you didn't
  notice/act," not every reminder.

## Consequences

### Positive

- Reminders that are actually ignored now get a second, much harder to
  miss escalation, directly addressing the PRD's re-engagement goal.
- Zero marginal cost and zero new external dependency — pure client-side
  Android code reusing infrastructure (AlarmManager, NotificationCompat)
  already exempt from most Doze/battery restrictions when used this way.
- Both tiers share one JS-side action handler, so "acted on it" is
  consistent everywhere and there's no code duplicated between Tier-1 and
  Tier-2 Snooze/Done handling.
- Cold-start-safe: even if the app process was fully killed and the OS
  only spun it up to show the ring, Snooze/Done still work via the
  persisted action queue.

### Negative

- **Battery-optimization / OEM caveats.** Even `setAlarmClock` can be
  undermined by aggressive third-party battery managers (common on some
  Chinese OEM skins — MIUI, ColorOS, etc.) that kill background alarms
  outright unless the app is manually exempted. This is a known,
  documented Android ecosystem problem with no full client-side fix;
  the manual verification checklist below calls out the exemption step.
- **DND bypass is not guaranteed.** Alarm-stream audio (`USAGE_ALARM`)
  typically bypasses Do Not Disturb, but this is device/OEM policy, not
  a hard platform guarantee — verify per device.
- **`USE_FULL_SCREEN_INTENT` requires a one-time user grant on Android
  14+**, and Play Store policy restricts this permission to
  legitimately alarm/call-like apps. If Overwatch is ever distributed
  via Play, this declaration will need Play Console justification.
- **No true "still open" check at fire time.** The alarm fires
  unconditionally once armed; "don't ring if already done" is enforced
  by proactively cancelling the Tier-2 alarm the moment Tier-1 (or
  Tier-2 itself) is acted on — not by re-querying commitment status
  inside the `BroadcastReceiver`. A commitment marked done through some
  *other* path (e.g. a different device, or a direct API call bypassing
  this app's own action handlers) between scheduling and fire time could
  still ring once. Acceptable for a single-device v1; a future version
  could have `RingAlarmReceiver` do a live status check before posting,
  at the cost of a network call from a `BroadcastReceiver`.
- **Tier-2's own reconciliation bookkeeping (localStorage id set) is
  best-effort**, unlike Tier-1's authoritative `getPending()` diff. A
  wiped localStorage (e.g. browser data cleared inside the WebView) could
  in principle leave a stale native alarm briefly un-cancelled until the
  next full sync reschedules over it with `FLAG_UPDATE_CURRENT`.

## References

- ADR-0007 (Web Push notifications) — the server-side/browser reminder
  channel; this ADR's Tier 1/Tier 2 are the native-Android counterpart.
- `frontend/src/lib/notifications.js` — Tier 1 (existing) + shared
  Snooze/Done handler (`applyReminderAction`).
- `frontend/src/lib/ringAlarm.js` — Tier 2 JS-side plugin wrapper,
  reconciliation, and settings.
- `frontend/src/components/SettingsPanel.jsx` — "Ring loudly if I miss a
  reminder" toggle + full-screen-intent permission prompt.
- `frontend/android/app/src/main/java/com/tanmayhatkar/overwatch/`:
  `RingAlarmPlugin.kt`, `RingAlarmReceiver.kt`, `RingActionReceiver.kt`,
  `RingActivity.kt`, `RingActionStore.kt`, `RingConstants.kt`.
- Android docs: `NotificationCompat.Builder#setFullScreenIntent`,
  `AlarmManager#setAlarmClock`, `NotificationManagerCompat#canUseFullScreenIntent`
  (API 34), `Settings#ACTION_MANAGE_APP_USE_FULL_SCREEN_INTENT`.
