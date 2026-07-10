/**
 * ringAlarm.js — Tier 2 "ring" escalation (ADR-0019).
 *
 * notifications.js's Tier-1 reminder is a normal, dismissible heads-up
 * notification — easy to swipe away without acting on it. This module adds
 * a Tier-2 fallback: if a commitment is still open ESCALATE_AFTER_MINUTES
 * after its Tier-1 reminder fired, the native RingAlarmPlugin (Android only)
 * shows a full-screen, ringtone-looping alarm — the "the phone actually
 * rings" experience.
 *
 * Android-only. No-op everywhere else (iOS/web have no equivalent
 * full-screen-intent API), guarded by isNative() throughout.
 */

import { registerPlugin } from '@capacitor/core'
import { isNative } from './native'
import { getSetting, setSetting } from './settings'

/** Minutes after due_at that Tier 2 rings, if the commitment is still open. */
export const ESCALATE_AFTER_MINUTES = 10

const SCHEDULED_IDS_KEY = 'overwatch.ring.scheduledIds'

const RingAlarm = registerPlugin('RingAlarm')

/** True if the user has opted into Tier-2 ring escalation (native only). */
export function isRingEscalationEnabled() {
  return isNative() && getSetting('ringEscalationEnabled')
}

/** Persist the ring-escalation toggle. Takes effect on the next reminder sync. */
export function setRingEscalationEnabled(enabled) {
  setSetting('ringEscalationEnabled', enabled)
}

/** Schedule (or replace) the Tier-2 ring alarm for a commitment. Best-effort. */
async function scheduleRing(id, commitmentId, title, body, atMillis) {
  if (!isNative()) return
  try {
    await RingAlarm.ring({ id, commitmentId, title, body, at: atMillis })
  } catch {
    // best-effort — a missed Tier-2 schedule shouldn't break Tier-1
  }
}

/** Cancel a pending (or already-firing) Tier-2 ring for a commitment id. Best-effort. */
export async function cancelRing(id) {
  if (!isNative()) return
  try {
    await RingAlarm.cancelRing({ id })
  } catch {
    // best-effort
  }
}

/** Android 14+ full-screen-intent permission state. True (n/a) on older APIs / non-native. */
export async function checkFullScreenIntentPermission() {
  if (!isNative()) return true
  try {
    const { granted } = await RingAlarm.checkFullScreenIntentPermission()
    return granted
  } catch {
    return true
  }
}

/** Deep-link to the OS settings screen to grant USE_FULL_SCREEN_INTENT (Android 14+). */
export async function openFullScreenIntentSettings() {
  if (!isNative()) return
  try {
    await RingAlarm.openFullScreenIntentSettings()
  } catch {
    // ignore
  }
}

function getScheduledIds() {
  try {
    return JSON.parse(localStorage.getItem(SCHEDULED_IDS_KEY) || '[]')
  } catch {
    return []
  }
}

function setScheduledIds(ids) {
  try {
    localStorage.setItem(SCHEDULED_IDS_KEY, JSON.stringify(ids))
  } catch {
    // ignore — worst case we re-cancel a stale id next sync, which is harmless
  }
}

/**
 * Reconcile Tier-2 ring alarms with the current open commitments — the
 * Tier-2 counterpart of syncCommitmentReminders(). AlarmManager has no
 * "list what's pending" API reachable from here (unlike Capacitor's
 * LocalNotifications.getPending(), which Tier 1 uses), so we track our own
 * previously scheduled ids in localStorage and cancel anything not in the
 * new set. Also fully clears when the user has the toggle off, so flipping
 * it off doesn't leave an orphaned alarm armed.
 *
 * @param {Array<{id: number, commitmentId: string, title: string, body: string, atMillis: number}>} entries
 */
export async function reconcileRingAlarms(entries) {
  if (!isNative()) return
  try {
    const previous = getScheduledIds()
    const enabled = isRingEscalationEnabled()
    const nextEntries = enabled ? entries : []
    const nextIds = nextEntries.map((e) => e.id)

    const toCancel = previous.filter((id) => !nextIds.includes(id))
    for (const id of toCancel) {
      await cancelRing(id)
    }
    for (const e of nextEntries) {
      await scheduleRing(e.id, e.commitmentId, e.title, e.body, e.atMillis)
    }
    setScheduledIds(nextIds)
  } catch {
    // best-effort — never let ring scheduling break the app
  }
}

/**
 * Wire up delivery of ring-screen Snooze/Done taps, both live (bridge
 * currently running) and queued (the app process was cold-started just to
 * show the ring, so nothing was listening yet).
 *
 * @param {(action: string, extra: {id: number, commitmentId: string}) => void} handler
 *   Pass the same handler notifications.js uses for its own Tier-1
 *   Snooze/Done actions, so both tiers share one code path.
 */
export async function initRingActionListener(handler) {
  if (!isNative()) return
  try {
    await RingAlarm.addListener('ringAction', (event) => {
      handler(event.action, { id: event.id, commitmentId: event.commitmentId })
    })
    const { actions } = await RingAlarm.drainPendingRingActions()
    for (const a of actions || []) {
      handler(a.action, { id: a.id, commitmentId: a.commitmentId })
    }
  } catch {
    // plugin unavailable — ignore
  }
}
