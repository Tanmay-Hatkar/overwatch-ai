/**
 * notifications.js — On-device commitment reminders (native alarm, Tier 1)
 * and the stale-plan check-in (ADR-0017), via expo-notifications.
 *
 * Direct port of frontend/src/lib/notifications.js's reconcile algorithm
 * (staleCheckFireAt, syncCommitmentReminders) onto the RN/Expo notification
 * API — the fire-time math and dedup logic are proven, only the native
 * binding layer changes. Ring escalation (Tier 2, ADR-0019) is a separate,
 * larger native-module port and deliberately not included here.
 *
 * expo-notifications schedules with the OS, same reliability story as the
 * old Capacitor LocalNotifications port: fires even if the app is closed,
 * no network round-trip, works offline. No-op on web (Platform.OS ===
 * 'web') -- local scheduling isn't meaningfully supported there.
 */
import { Platform } from 'react-native'
import * as Notifications from 'expo-notifications'
import { updateCommitment } from '../api'

const CHANNEL_ID = 'reminders'
const CATEGORY_ID = 'COMMITMENT_REMINDER'
const SNOOZE_MINUTES = 10

// Must match backend/app/config.py's stale_check_threshold_hours default --
// the CLIENT-side half of ADR-0017's "one-time check-in." Not fetched from
// the server (no public settings endpoint); drift only means the client's
// schedule is off by however much an admin has changed the backend
// default -- rare and low-stakes, since the server remains the dedup
// source of truth.
const STALE_CHECK_THRESHOLD_HOURS = 4

function isSupported() {
  return Platform.OS !== 'web'
}

/**
 * Stable identifier for a commitment's due-time reminder. expo-notifications
 * identifiers are arbitrary strings (unlike Capacitor's LocalNotifications,
 * which needed a 31-bit int) -- no hashing needed, just a namespaced string.
 * Exported so a future Tier-2 (ring) port can correlate to the same id.
 */
export function notifId(commitmentId) {
  return `reminder:${commitmentId}`
}

/** Distinct id for a commitment's stale-check notification -- deliberately
 * different from notifId() since both can be scheduled for the same
 * commitment at once. */
function staleCheckNotifId(commitmentId) {
  return `stale:${commitmentId}`
}

/**
 * Create the high-importance Android notification channel reminders use.
 * Without an explicit HIGH-importance channel, Android may show reminders
 * silently or not as a heads-up. Idempotent; Android-only (no-op on iOS).
 */
async function ensureChannel() {
  if (!isSupported() || Platform.OS !== 'android') return
  try {
    await Notifications.setNotificationChannelAsync(CHANNEL_ID, {
      name: 'Reminders',
      description: 'Commitment reminders and alarms',
      importance: Notifications.AndroidImportance.HIGH,
      lockscreenVisibility: Notifications.AndroidNotificationVisibility.PUBLIC,
      vibrationPattern: [0, 250, 250, 250],
    })
  } catch {
    // ignore -- channel setup failing shouldn't break the app
  }
}

/** Register the Snooze/Done quick actions shown on the reminder notification. */
async function ensureCategory() {
  if (!isSupported()) return
  try {
    await Notifications.setNotificationCategoryAsync(CATEGORY_ID, [
      { identifier: 'SNOOZE', buttonTitle: `Snooze ${SNOOZE_MINUTES} min` },
      { identifier: 'DONE', buttonTitle: 'Mark done' },
    ])
  } catch {
    // ignore
  }
}

/** Ask for notification permission (required on Android 13+ and iOS).
 * Returns true if granted. */
export async function ensureNotificationPermission() {
  if (!isSupported()) return false
  try {
    const existing = await Notifications.getPermissionsAsync()
    if (existing.granted) return true
    const requested = await Notifications.requestPermissionsAsync()
    return requested.granted
  } catch {
    return false
  }
}

/** Humanize a lead time for the notification body ("15 min", "1 hr"). */
function humanizeLead(minutes) {
  if (minutes >= 60 && minutes % 60 === 0) return `${minutes / 60} hr`
  return `${minutes} min`
}

/** Epoch millis for local midnight of the given ISO date's calendar day. */
function startOfLocalDay(iso) {
  const d = new Date(iso)
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
}

/**
 * When a commitment's one-time stale-plan check-in (ADR-0017) should fire,
 * mirroring backend/app/repositories/commitment_repository.py's
 * list_stale_candidates SQL: dormant for STALE_CHECK_THRESHOLD_HOURS since
 * updated_at, AND (no due date, OR due date is today or earlier). The fire
 * time is the LATER of "dormant long enough" and "due date has arrived" --
 * a future-dated commitment can't qualify before its due date, however
 * dormant it's been.
 *
 * @param {{due_at: string|null, updated_at: string}} c
 * @returns {number} epoch millis
 */
export function staleCheckFireAt(c) {
  const dormantAt = new Date(c.updated_at).getTime() + STALE_CHECK_THRESHOLD_HOURS * 3_600_000
  if (!c.due_at) return dormantAt
  return Math.max(dormantAt, startOfLocalDay(c.due_at))
}

/**
 * Shared Snooze/Done handler. SNOOZE reschedules the same reminder
 * ~10 min later; DONE marks the commitment done via the API (best-effort).
 *
 * @param {'SNOOZE'|'DONE'} actionId
 * @param {{id?: string, commitmentId?: string, text?: string, reminderPhrase?: string|null}} extra
 */
async function applyReminderAction(actionId, extra) {
  const id = extra.id ?? (extra.commitmentId ? notifId(extra.commitmentId) : undefined)

  if (actionId === 'SNOOZE') {
    try {
      await Notifications.scheduleNotificationAsync({
        identifier: id,
        content: {
          title: 'Overwatch',
          body: extra.reminderPhrase || `Still pending: ${extra.text || 'your commitment'}`,
          categoryIdentifier: CATEGORY_ID,
          data: extra,
        },
        trigger: {
          type: Notifications.SchedulableTriggerInputTypes.DATE,
          date: new Date(Date.now() + SNOOZE_MINUTES * 60_000),
        },
      })
    } catch {
      // best-effort
    }
  } else if (actionId === 'DONE' && extra.commitmentId) {
    try {
      await updateCommitment(extra.commitmentId, { status: 'done' })
    } catch {
      // ignore -- the user can mark it done in-app later
    }
  }
}

/**
 * Register the notification-response listener that reacts to Snooze/Done
 * taps. Call once at app init (after sign-in). Returns an unsubscribe
 * function.
 */
export async function initNotificationActions() {
  if (!isSupported()) return () => {}
  await ensureChannel()
  await ensureCategory()

  const subscription = Notifications.addNotificationResponseReceivedListener(async (response) => {
    const actionId = response.actionIdentifier
    const data = response.notification.request.content.data || {}
    const id = response.notification.request.identifier
    if (actionId === 'SNOOZE' || actionId === 'DONE') {
      await applyReminderAction(actionId, { ...data, id })
    }
  })

  return () => subscription.remove()
}

/**
 * Reconcile scheduled reminders with the current commitments. Cancels
 * everything previously scheduled, then schedules one reminder per OPEN
 * commitment with a due time (fires at due_at - reminder_lead_minutes),
 * plus one stale-check notification per OPEN commitment the server hasn't
 * already asked about (stale_check_sent_at is null). Call whenever the
 * commitments list loads or changes so the OS schedule always matches
 * reality.
 *
 * Uses reminder_phrase (ADR-0021) as the reminder body when present,
 * falling back to a templated string for commitments created before that
 * field existed.
 */
export async function syncCommitmentReminders(commitments) {
  if (!isSupported()) return
  try {
    await Notifications.cancelAllScheduledNotificationsAsync()

    const now = Date.now()
    const open = commitments.filter((c) => c.status === 'open')
    const openWithDueDate = open.filter((c) => c.due_at)

    const reminders = openWithDueDate
      .map((c) => {
        const lead = Math.max(0, c.reminder_lead_minutes || 0)
        const fireAt = new Date(c.due_at).getTime() - lead * 60_000
        return { c, lead, fireAt }
      })
      .filter(({ fireAt }) => fireAt > now)
      .map(({ c, lead, fireAt }) => ({
        identifier: notifId(c.id),
        content: {
          title: 'Overwatch',
          body:
            c.reminder_phrase ||
            (lead > 0 ? `In ${humanizeLead(lead)}: ${c.text}` : `Time to start: ${c.text}`),
          categoryIdentifier: CATEGORY_ID,
          data: { commitmentId: c.id, text: c.text, reminderPhrase: c.reminder_phrase || null },
        },
        trigger: { type: Notifications.SchedulableTriggerInputTypes.DATE, date: new Date(fireAt) },
      }))

    const staleChecks = open
      .filter((c) => !c.stale_check_sent_at)
      .map((c) => ({ c, fireAt: staleCheckFireAt(c) }))
      .filter(({ fireAt }) => fireAt > now)
      .map(({ c, fireAt }) => ({
        identifier: staleCheckNotifId(c.id),
        content: {
          title: 'Overwatch',
          body: `Still the plan — "${c.text}"? Or has today changed?`,
          data: { commitmentId: c.id, text: c.text, staleCheck: true },
        },
        trigger: { type: Notifications.SchedulableTriggerInputTypes.DATE, date: new Date(fireAt) },
      }))

    for (const request of [...reminders, ...staleChecks]) {
      await Notifications.scheduleNotificationAsync(request)
    }
  } catch {
    // best-effort -- never let reminder scheduling break the app
  }
}
