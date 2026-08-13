/**
 * ringAlarm.js — Tier 2 "ring" escalation (ADR-0019).
 *
 * notifications.js's Tier-1 reminder is a normal, dismissible heads-up
 * notification -- easy to swipe away without acting on it. This module adds
 * a Tier-2 fallback: if a commitment is still open ESCALATE_AFTER_MINUTES
 * after its due time, the native RingAlarm module (Android only, at
 * modules/ring-alarm) shows a full-screen, ringtone-looping alarm -- the
 * "the phone actually rings" experience. Direct port of
 * frontend/src/lib/ringAlarm.js's reconcile algorithm onto that module.
 *
 * Android-only. No-op everywhere else -- iOS has no equivalent full-screen-
 * intent API, and the module's web stub also just no-ops.
 */
import { Platform } from 'react-native'
import * as SecureStore from 'expo-secure-store'
import RingAlarm from '../../modules/ring-alarm'
import { notifId, applyReminderAction } from './notifications'

/** Minutes after due_at that Tier 2 rings, if the commitment is still open. */
export const ESCALATE_AFTER_MINUTES = 10

const SCHEDULED_IDS_KEY = 'ow.ring.scheduledIds'
const ENABLED_KEY = 'ow.ring.enabled'

function isSupported() {
  return Platform.OS === 'android'
}

/** True if the user has opted into Tier-2 ring escalation. Android-only, default on. */
export async function isRingEscalationEnabled() {
  if (!isSupported()) return false
  try {
    const stored = await SecureStore.getItemAsync(ENABLED_KEY)
    return stored === null ? true : stored === 'true'
  } catch {
    return true
  }
}

/** Persist the ring-escalation toggle. Takes effect on the next reminder sync. */
export async function setRingEscalationEnabled(enabled) {
  if (!isSupported()) return
  try {
    await SecureStore.setItemAsync(ENABLED_KEY, String(enabled))
  } catch {
    // ignore
  }
}

async function getScheduledIds() {
  try {
    const raw = await SecureStore.getItemAsync(SCHEDULED_IDS_KEY)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

async function setScheduledIds(ids) {
  try {
    await SecureStore.setItemAsync(SCHEDULED_IDS_KEY, JSON.stringify(ids))
  } catch {
    // ignore -- worst case we re-cancel a stale id next sync, which is harmless
  }
}

/**
 * AlarmManager needs a 32-bit int id; commitment ids are UUID strings. This
 * is a stable, deterministic string hash (not cryptographic) -- collisions
 * are theoretically possible but vanishingly unlikely at the scale of one
 * user's open commitments.
 */
function numericRingId(commitmentId) {
  let hash = 0
  for (let i = 0; i < commitmentId.length; i++) {
    hash = (hash * 31 + commitmentId.charCodeAt(i)) | 0
  }
  return hash & 0x7fffffff
}

/** Schedule (or replace) the Tier-2 ring alarm for a commitment. Best-effort. */
async function scheduleRing(id, commitmentId, title, body, atMillis) {
  if (!isSupported()) return
  try {
    await RingAlarm.ring(id, commitmentId, title, body, atMillis)
  } catch {
    // best-effort -- a missed Tier-2 schedule shouldn't break Tier-1
  }
}

/** Cancel a pending (or already-firing) Tier-2 ring for a numeric ring id. Best-effort. */
export async function cancelRing(id) {
  if (!isSupported()) return
  try {
    await RingAlarm.cancelRing(id)
  } catch {
    // best-effort
  }
}

/** Android 14+ full-screen-intent permission state. True (n/a) on older APIs / non-Android. */
export async function checkFullScreenIntentPermission() {
  if (!isSupported()) return true
  try {
    return await RingAlarm.checkFullScreenIntentPermission()
  } catch {
    return true
  }
}

/** Deep-link to the OS settings screen to grant USE_FULL_SCREEN_INTENT (Android 14+). */
export async function openFullScreenIntentSettings() {
  if (!isSupported()) return
  try {
    await RingAlarm.openFullScreenIntentSettings()
  } catch {
    // ignore
  }
}

/**
 * Reconcile Tier-2 ring alarms with the current open commitments -- the
 * Tier-2 counterpart of syncCommitmentReminders(). Fires
 * ESCALATE_AFTER_MINUTES after each commitment's due_at (deliberately not
 * layered on top of reminder_lead_minutes -- the escalation is "still open
 * past the actual deadline," not "past the heads-up"). Skips commitments
 * with no due date -- there's no fixed instant to escalate against.
 * AlarmManager has no "list what's pending" API reachable from here (unlike
 * expo-notifications' getAllScheduledNotificationsAsync, which Tier 1
 * uses), so previously scheduled ids are tracked in SecureStore and
 * anything not in the new set gets cancelled.
 *
 * @param {Array<{id: string, status: string, due_at: string|null, text: string, reminder_phrase: string|null}>} commitments
 */
export async function reconcileRingAlarms(commitments) {
  if (!isSupported()) return
  try {
    const enabled = await isRingEscalationEnabled()
    const previous = await getScheduledIds()

    const open = commitments.filter((c) => c.status === 'open' && c.due_at)
    const nextEntries = enabled
      ? open.map((c) => ({
          id: numericRingId(c.id),
          commitmentId: c.id,
          title: 'Overwatch',
          body: c.reminder_phrase || `Still pending: ${c.text}`,
          atMillis: new Date(c.due_at).getTime() + ESCALATE_AFTER_MINUTES * 60_000,
        }))
      : []
    const nextIds = nextEntries.map((e) => e.id)

    const toCancel = previous.filter((id) => !nextIds.includes(id))
    for (const id of toCancel) {
      await cancelRing(id)
    }
    for (const e of nextEntries) {
      await scheduleRing(e.id, e.commitmentId, e.title, e.body, e.atMillis)
    }
    await setScheduledIds(nextIds)
  } catch {
    // best-effort -- never let ring scheduling break the app
  }
}

/**
 * Wire up delivery of ring-screen Snooze/Done taps, both live (bridge
 * currently running) and queued (the app process was cold-started just to
 * show the ring, so nothing was listening yet). Reuses
 * notifications.js's applyReminderAction so both tiers share one Snooze/Done
 * code path. Call once at app init (after sign-in), mirroring
 * initNotificationActions(). Returns an unsubscribe function.
 */
export function initRingActionListener() {
  if (!isSupported()) return () => {}

  const subscription = RingAlarm.addListener('ringAction', (event) => {
    applyReminderAction(event.action, {
      id: notifId(event.commitmentId),
      commitmentId: event.commitmentId,
    })
  })

  RingAlarm.drainPendingRingActions()
    .then((actions) => {
      for (const a of actions || []) {
        applyReminderAction(a.action, { id: notifId(a.commitmentId), commitmentId: a.commitmentId })
      }
    })
    .catch(() => {
      // plugin unavailable -- ignore
    })

  return () => subscription.remove()
}
