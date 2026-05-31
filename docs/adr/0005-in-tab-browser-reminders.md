# 0005: In-tab browser reminders via Web Notification API

- **Status:** Accepted
- **Date:** 2026-05-28
- **Deciders:** Tanmay Hatkar

## Context

The PRD's novel mechanic has two halves:

1. **Capture commitments from natural language** — shipped in slice 3.
2. **Surgically follow up at the time you said** — the missing half.

Without follow-up, Overwatch is a nice todo app + briefing generator. With follow-up, it's the product the PRD describes: an assistant that holds you to your own word at the moment you said.

Slice 5 needed to implement "follow-up" for the web app context. Several form-factor questions surfaced:

- **Where do reminders fire?** Browser-only is limited (browser must be open). Mobile push is right but requires native or PWA work. Desktop notifications work via OS-level APIs but only when the user is at their computer.
- **What channel?** Visual UI badge, browser notification, sound, all of the above?
- **How often to check?** Real-time (WebSockets) vs polling.
- **What about already-overdue items?** Fire a notification storm at mount? Suppress them?

Constraint for slice 5: **keep it scoped to the web app.** PWA-ification, mobile native, and desktop apps are deferred to later slices. Slice 5 ships the simplest version of the mechanic that demonstrates the product thesis.

## Decision

**Build in-tab reminders using the Web Notification API.** A custom React hook polls every 60 seconds for newly-due commitments and fires browser notifications. Permission is requested via an opt-in UI element. Already-overdue items at mount are suppressed.

### Implementation shape

`frontend/src/hooks/useReminders.js`:

```javascript
export function useReminders(commitments) {
  const notifiedIds = useRef(new Set())
  const isFirstCheck = useRef(true)

  useEffect(() => {
    if (typeof Notification === 'undefined') return
    if (Notification.permission !== 'granted') return

    function check() {
      const now = Date.now()
      for (const c of commitments) {
        if (c.status !== 'open' || !c.due_at) continue
        if (notifiedIds.current.has(c.id)) continue

        const due = new Date(c.due_at).getTime()
        if (due > now) continue

        if (isFirstCheck.current) {
          notifiedIds.current.add(c.id)  // suppress
        } else {
          new Notification('Overwatch', {
            body: `You said you'd: ${c.text}`,
            tag: c.id,
            requireInteraction: true,
          })
          notifiedIds.current.add(c.id)
        }
      }
      isFirstCheck.current = false
    }

    check()
    const interval = setInterval(check, 60 * 1000)
    return () => clearInterval(interval)
  }, [commitments])
}
```

Plus a `NotificationStatus` component that prompts for permission when state is `default`, displays a "blocked" note when `denied`, and renders nothing when `granted`.

### Key sub-decisions

**1. Polling at 60-second intervals, not WebSocket.**
The web app already re-fetches commitments after every mutation. Reminders just hook into the same in-memory commitments list. Polling adds no server load (it's client-side) and 60-second resolution is fine for human-scale commitments. WebSockets would be overkill.

**2. Suppress notifications for already-overdue items on first check.**
Opening the app with 5 overdue commitments shouldn't fire 5 notifications. The user can see them visually (red borders, briefing card). Reminders are for items that become NEWLY overdue during the session — that's the "surgical follow-up" the PRD describes.

**3. `requireInteraction: true`.**
Default browser notifications auto-dismiss after a few seconds. Productivity reminders deserve attention — they stay visible until clicked. Worth the slightly more intrusive UX.

**4. `tag: c.id` for deduplication.**
If the same commitment somehow triggers two notifications (e.g., the hook re-renders), the second replaces the first instead of stacking. Belt-and-suspenders alongside `notifiedIds`.

**5. Permission flow is opt-in, not on-mount auto-request.**
A `NotificationStatus` component shows a subtle "Enable reminders →" link. Clicking it triggers the permission prompt. Reasons: (a) users hate getting an immediate "this site wants to send notifications" popup; (b) the user should understand WHAT they're enabling before granting; (c) the link is a UI affordance that's discoverable but unobtrusive.

**6. `notifiedIds` lives in a `useRef`, not state.**
We don't want re-renders when an id is added to the set. A ref is the right primitive for "mutable cross-render state that doesn't trigger re-render."

## Alternatives considered

### Server-side scheduler (cron / APScheduler)

A backend job that checks for due commitments every minute and pushes notifications to clients.

**Rejected because:**
- Requires a delivery channel (WebSocket, Server-Sent Events, Push API with VAPID)
- Hosting requirement — the backend has to be always-running on a server, not just localhost
- Slice 5 is scoped to "web app while open," not "always running, push to user wherever they are"
- This is the right architecture for the *eventual* mobile/PWA version, but premature for slice 5

### WebSocket-based live updates

Keep an open connection between frontend and backend. Backend pushes "commitment is due" events.

**Rejected because:**
- Overkill for a single-user local app
- Adds infrastructure (WebSocket library on both sides, connection management)
- 60-second client-side polling achieves the same UX with no server changes

### Audio alert in addition to (or instead of) browser notification

Play a sound when a commitment becomes due.

**Deferred:** browser notifications can already have a sound (browser-controlled, OS-level). A custom sound layer would be a separate slice. Browsers also have varying support for audio without user interaction first. Not worth the complexity in slice 5.

### Real-time UI updates instead of notifications

Just visually highlight the newly-overdue item in the UI when it becomes due. No browser notification.

**Rejected because:**
- Requires the user to be looking at the app
- That's exactly what the PRD argues against ("plans die from neglect" — neglect = not looking)
- Visual highlight is fine as a supplement (it already happens via the red border for overdue), but not as a replacement

### Service worker + push notifications now

Implement push notifications via VAPID + service worker so notifications fire even when the tab is closed.

**Deferred to a future "PWA-ification" slice.** Service workers need a separate file, registration flow, and the PWA manifest. Big enough to be its own slice. Slice 5 ships the in-tab version first as the foundation.

## Consequences

### Positive

- **Completes the PRD's novel mechanic.** Capture + surgical follow-up is now end-to-end in the web app.
- **Zero backend changes required.** Pure frontend feature. Backend doesn't need to know about notifications.
- **No new dependencies.** Uses only browser-native APIs (Notification, setInterval, ref-tracked state).
- **No notification spam at mount.** First-check suppression handles the obvious failure mode.
- **Respects user attention.** Opt-in permission, `requireInteraction` for important events, clear "Enable reminders" affordance.
- **Easy to upgrade.** When PWA-ification arrives, the same `useReminders` hook can be augmented to register a service worker, and existing notification call sites need no changes.

### Negative

- **Only works when the tab is open.** Close the tab → no reminders fire. This is the inherent limitation of in-tab notifications and is why PWA-ification matters as a follow-up.
- **Polling overhead.** Every 60 seconds, the hook iterates through the commitments list. At our scale (dozens of commitments) this is microseconds. At 10,000 commitments, we'd reconsider.
- **Browser permission UX is awkward.** Some users will deny permission and never come back. The `NotificationStatus` "blocked" message tries to recover this but most users won't dig into browser settings to fix it. Real solution: have users on PWA where mobile OS permissions feel more natural.
- **No snooze functionality.** A "remind me in 10 minutes" pattern would require state we don't track. Can add later as a separate slice.
- **iOS Safari has weaker support** for some notification features (no `requireInteraction` until recent versions, limited PWA push). Affects future PWA work; not blocking for slice 5.

### Future considerations

- **PWA + push.** Next major step. Service worker handles notifications when the tab is closed. iOS support has improved a lot in 2024–2025 but still trails Android.
- **Snooze.** Allow the user to dismiss a notification with "remind me in N minutes" instead of just clicking through. Requires a backend-tracked snooze state per commitment, or local-state-only if we accept it doesn't survive page reload.
- **Notification customization in Settings.** Toggle on/off, quiet hours, sound preferences.
- **Backend mirror.** When/if there's a backend scheduler, it could send the same notifications via Web Push so reminders fire even when the tab is closed AND the device is asleep. Eventually-needed for real reliability.
- **Stats hook.** Track which notifications the user actually acts on (clicks vs ignores). Feeds into pattern recognition slice.

## References

- The hook: `frontend/src/hooks/useReminders.js`
- The permission UI: `frontend/src/components/NotificationStatus.jsx`
- MDN Notification API: https://developer.mozilla.org/en-US/docs/Web/API/Notification
- Web Push for the future PWA path: https://web.dev/articles/push-notifications-overview
- Implementation commit: `581f465` ("feat(reminders): in-tab browser notifications when commitments become due")
- PRD section that this implements: "novel mechanic — surgical follow-up at the time you said"
