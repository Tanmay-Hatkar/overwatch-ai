/**
 * notifications.js — On-device commitment reminders (native alarm, Tier 1).
 *
 * Uses Capacitor LocalNotifications: the reminder is scheduled with the
 * Android OS, so it fires at the commitment's due time even if the app is
 * closed or killed (the OS holds the schedule — we don't keep the app
 * running). This is more reliable on the native app than server push:
 * no network round-trip, exact timing, works offline.
 *
 * Actions on the notification:
 *   - Snooze → reschedules the same reminder ~10 min later (it "buzzes again")
 *   - Done   → marks the commitment done via the API (best-effort)
 *
 * Everything here is a no-op on the web build (isNative() === false), where
 * web push handles reminders instead.
 *
 * Tier 2 (ADR-0019, see ./ringAlarm.js) piggybacks on this file: it shares
 * the same Snooze/Done handler (applyReminderAction below) and the same
 * per-commitment integer id (notifId), so a Snooze/Done tap on EITHER tier's
 * UI resolves both — no orphaned full-screen ring left armed after the user
 * has already acted on the ordinary notification.
 */

import { LocalNotifications } from '@capacitor/local-notifications'
import { isNative } from './native'
import { updateCommitment } from '../api'
import { ESCALATE_AFTER_MINUTES, cancelRing, initRingActionListener, reconcileRingAlarms } from './ringAlarm'

const ACTION_TYPE = 'COMMITMENT_REMINDER'
const CHANNEL_ID = 'reminders'
const SNOOZE_MINUTES = 10

/**
 * Create the high-importance Android notification channel reminders use.
 * Without an explicit HIGH channel, Android may show reminders silently or
 * not as a heads-up. Idempotent; Android-only (no-op elsewhere).
 */
async function ensureChannel() {
  if (!isNative()) return
  try {
    await LocalNotifications.createChannel({
      id: CHANNEL_ID,
      name: 'Reminders',
      description: 'Commitment reminders and alarms',
      importance: 5, // HIGH — heads-up with sound
      visibility: 1, // public on lock screen
      vibration: true,
    })
  } catch {
    // createChannel is Android-only; ignore on iOS / if unavailable
  }
}

/**
 * Derive a stable 31-bit integer id from a commitment UUID (plugin needs int
 * ids). Exported: ringAlarm.js uses the exact same id so a Tier-1 and Tier-2
 * alarm for the same commitment always correlate.
 */
export function notifId(uuid) {
  let h = 0
  for (let i = 0; i < uuid.length; i++) {
    h = (h * 31 + uuid.charCodeAt(i)) | 0
  }
  return Math.abs(h) % 2147483647
}

/** Ask for notification permission (Android 13+). Returns true if granted. */
export async function ensureNotificationPermission() {
  if (!isNative()) return false
  try {
    const perm = await LocalNotifications.requestPermissions()
    return perm.display === 'granted'
  } catch {
    return false
  }
}

/** True only inside the native app (where local-notification alarms work). */
export function notificationsAreNative() {
  return isNative()
}

/**
 * Fire a test reminder ~8 seconds from now so the user can verify the native
 * alarm pipeline (permission + scheduling) without waiting for a real due time.
 * Returns a short status string for the UI.
 */
export async function sendTestNotification() {
  if (!isNative()) {
    return 'Test alarms only work in the installed Android app, not the browser.'
  }
  if (!LocalNotifications || typeof LocalNotifications.schedule !== 'function') {
    return 'Notifications plugin missing — do a clean rebuild in Android Studio.'
  }
  try {
    const granted = await ensureNotificationPermission()
    if (!granted) {
      return 'Permission is OFF. Android settings → Apps → Overwatch → Notifications → allow.'
    }
    await ensureChannel()
    // Deliberately minimal (no action types) so this isolates the core path.
    await LocalNotifications.schedule({
      notifications: [
        {
          id: 999000,
          title: 'Overwatch — test',
          body: 'If you see this, alarms work.',
          channelId: CHANNEL_ID,
          schedule: { at: new Date(Date.now() + 8000), allowWhileIdle: true },
        },
      ],
    })
    return 'Scheduled ✓ — lock your phone, it fires in ~8s. (No popup = exact-alarm setting.)'
  } catch (e) {
    return `Schedule failed: ${e?.message || e}`
  }
}

/**
 * Shared Snooze/Done handler for BOTH tiers. The Tier-1 notification action
 * and the Tier-2 ring screen/fallback-notification action funnel into this
 * one function so "acted on it" means the same thing everywhere:
 *   - SNOOZE → reschedule the Tier-1 reminder ~10 min later
 *   - DONE   → mark the commitment done via the API (best-effort)
 *   - either → cancel any still-pending Tier-2 ring for this commitment, so
 *     acting on Tier 1 (or the ring itself) never leaves an orphaned alarm
 *     armed for later (ADR-0019).
 *
 * @param {string} actionId  'SNOOZE' | 'DONE'
 * @param {{id?: number, commitmentId?: string, text?: string}} extra
 */
async function applyReminderAction(actionId, extra) {
  const id = extra.id ?? (extra.commitmentId ? notifId(extra.commitmentId) : undefined)

  if (actionId === 'SNOOZE') {
    // Reschedule the same reminder → it rings again after the interval.
    await LocalNotifications.schedule({
      notifications: [
        {
          id: id ?? Date.now() % 2147483647,
          title: 'Overwatch',
          body: extra.reminderPhrase || `Still pending: ${extra.text || 'your commitment'}`,
          schedule: {
            at: new Date(Date.now() + SNOOZE_MINUTES * 60_000),
            allowWhileIdle: true,
          },
          actionTypeId: ACTION_TYPE,
          extra,
        },
      ],
    })
  } else if (actionId === 'DONE' && extra.commitmentId) {
    // Mark done without opening the app (best-effort).
    try {
      await updateCommitment(extra.commitmentId, { status: 'done' })
    } catch {
      // ignore — the user can mark it done in-app later
    }
  }

  if (id !== undefined) {
    await cancelRing(id)
  }
}

/**
 * Register the Snooze/Done actions and the handler that reacts to them.
 * Call once at app init (after sign-in).
 */
export async function initNotificationActions() {
  if (!isNative()) return
  try {
    await ensureChannel()
    await LocalNotifications.registerActionTypes({
      types: [
        {
          id: ACTION_TYPE,
          actions: [
            { id: 'SNOOZE', title: `Snooze ${SNOOZE_MINUTES} min` },
            { id: 'DONE', title: 'Mark done' },
          ],
        },
      ],
    })

    await LocalNotifications.addListener(
      'localNotificationActionPerformed',
      async (event) => {
        const { actionId, notification } = event
        const extra = notification.extra || {}
        await applyReminderAction(actionId, { ...extra, id: notification.id })
      },
    )

    // Tier 2 (ADR-0019): Snooze/Done taps made on the ring screen or its
    // fallback notification funnel back through the same handler.
    await initRingActionListener(applyReminderAction)
  } catch {
    // plugin unavailable / not native — ignore
  }
}

/** Humanize a lead time for the notification body ("15 min", "1 hr"). */
function humanizeLead(minutes) {
  if (minutes >= 60 && minutes % 60 === 0) {
    const h = minutes / 60
    return `${h} hr`
  }
  return `${minutes} min`
}

/**
 * Reconcile scheduled reminders with the current commitments.
 *
 * Cancels everything previously scheduled, then schedules one reminder per
 * OPEN commitment with a due time. Each fires at (due_at − reminder_lead_minutes):
 *   - lead 0  → exactly at the due time (an alarm: "Time to start: X")
 *   - lead >0 → a heads-up that many minutes before ("In 15 min: X")
 * When the commitment has a `reminder_phrase` (ADR-0021 — a natural,
 * specific-recall check-in generated by the backend parser), it's used as
 * the body instead of the templated strings above. Commitments created
 * before that field existed have `reminder_phrase == null` and keep the
 * old templated behavior.
 * Call whenever the commitments list loads or changes so the OS schedule
 * always matches reality.
 *
 * Also reconciles the Tier-2 ring escalation (ADR-0019): for the same open
 * commitments, a companion ring alarm is (re)armed for
 * due_at + ESCALATE_AFTER_MINUTES. It only actually rings if the commitment
 * is still open at that time — but note the *scheduling* happens
 * unconditionally here; the "still open" check is enforced by cancelRing
 * being called from applyReminderAction the moment the user acts on either
 * tier (see above), not by re-checking status at fire time.
 */
export async function syncCommitmentReminders(commitments) {
  if (!isNative()) return
  try {
    const pending = await LocalNotifications.getPending()
    if (pending.notifications.length) {
      await LocalNotifications.cancel({
        notifications: pending.notifications.map((n) => ({ id: n.id })),
      })
    }

    const now = Date.now()
    const openWithDueDate = commitments.filter((c) => c.status === 'open' && c.due_at)

    const toSchedule = openWithDueDate
      .map((c) => {
        const lead = Math.max(0, c.reminder_lead_minutes || 0)
        const fireAt = new Date(c.due_at).getTime() - lead * 60_000
        return { c, lead, fireAt }
      })
      // Only schedule if the fire time (after subtracting the lead) is still ahead.
      .filter(({ fireAt }) => fireAt > now)
      .map(({ c, lead, fireAt }) => ({
        id: notifId(c.id),
        title: 'Overwatch',
        body:
          c.reminder_phrase ||
          (lead > 0 ? `In ${humanizeLead(lead)}: ${c.text}` : `Time to start: ${c.text}`),
        channelId: CHANNEL_ID,
        schedule: { at: new Date(fireAt), allowWhileIdle: true },
        actionTypeId: ACTION_TYPE,
        extra: { commitmentId: c.id, text: c.text, reminderPhrase: c.reminder_phrase || null },
      }))

    if (toSchedule.length) {
      await LocalNotifications.schedule({ notifications: toSchedule })
    }

    const ringEntries = openWithDueDate
      .map((c) => ({
        c,
        ringAt: new Date(c.due_at).getTime() + ESCALATE_AFTER_MINUTES * 60_000,
      }))
      .filter(({ ringAt }) => ringAt > now)
      .map(({ c, ringAt }) => ({
        id: notifId(c.id),
        commitmentId: c.id,
        title: 'Overwatch — still pending',
        body: c.reminder_phrase || c.text,
        atMillis: ringAt,
      }))

    await reconcileRingAlarms(ringEntries)
  } catch {
    // best-effort — never let reminder scheduling break the app
  }
}
