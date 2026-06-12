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
 */

import { LocalNotifications } from '@capacitor/local-notifications'
import { isNative } from './native'
import { updateCommitment } from '../api'

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

/** Derive a stable 31-bit integer id from a commitment UUID (plugin needs int ids). */
function notifId(uuid) {
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

        if (actionId === 'SNOOZE') {
          // Reschedule the same reminder → it rings again after the interval.
          await LocalNotifications.schedule({
            notifications: [
              {
                id: notification.id,
                title: 'Overwatch',
                body: `Still pending: ${extra.text || 'your commitment'}`,
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
      },
    )
  } catch {
    // plugin unavailable / not native — ignore
  }
}

/**
 * Reconcile scheduled reminders with the current commitments.
 *
 * Cancels everything previously scheduled, then schedules one reminder per
 * OPEN commitment whose due time is in the future. Call whenever the
 * commitments list loads or changes, so the OS schedule always matches reality.
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
    const toSchedule = commitments
      .filter(
        (c) =>
          c.status === 'open' &&
          c.due_at &&
          new Date(c.due_at).getTime() > now,
      )
      .map((c) => ({
        id: notifId(c.id),
        title: 'Overwatch',
        body: `Time to start: ${c.text}`,
        channelId: CHANNEL_ID,
        schedule: { at: new Date(c.due_at), allowWhileIdle: true },
        actionTypeId: ACTION_TYPE,
        extra: { commitmentId: c.id, text: c.text },
      }))

    if (toSchedule.length) {
      await LocalNotifications.schedule({ notifications: toSchedule })
    }
  } catch {
    // best-effort — never let reminder scheduling break the app
  }
}
