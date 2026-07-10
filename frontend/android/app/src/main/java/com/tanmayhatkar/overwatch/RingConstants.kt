package com.tanmayhatkar.overwatch

/**
 * Shared constants for the Tier-2 "ring" escalation feature (ADR-0019).
 *
 * Centralized here so the plugin, the alarm receiver, the action receiver,
 * and the ring activity all agree on channel/action/extra names without
 * hardcoding strings in more than one place.
 */
object RingConstants {

    /** Notification channel used for the (fallback / always-posted) ring notification. */
    const val CHANNEL_ID = "ring_alarm"

    /** Fired by AlarmManager when a scheduled ring goes off. Handled by [RingAlarmReceiver]. */
    const val ACTION_ALARM_FIRED = "com.tanmayhatkar.overwatch.action.RING_ALARM_FIRED"

    /** Sent by the fallback notification's actions or by RingActivity's buttons. Handled by [RingActionReceiver]. */
    const val ACTION_RING_BUTTON = "com.tanmayhatkar.overwatch.action.RING_BUTTON"

    /** Re-broadcast by [RingActionReceiver] so a live JS bridge can react immediately. */
    const val ACTION_RING_AVAILABLE = "com.tanmayhatkar.overwatch.action.RING_ACTION_AVAILABLE"

    /** Sent to tell an on-screen [RingActivity] to stop ringing (e.g. cancelled from JS). */
    const val ACTION_STOP_RING = "com.tanmayhatkar.overwatch.action.STOP_RING"

    // Intent extra keys
    const val EXTRA_ID = "id"
    const val EXTRA_COMMITMENT_ID = "commitmentId"
    const val EXTRA_TITLE = "title"
    const val EXTRA_BODY = "body"
    /** "SNOOZE" | "DONE" */
    const val EXTRA_ACTION = "action"

    // Persisted queue (SharedPreferences) for actions taken while the JS bridge was not alive.
    const val PREFS_NAME = "overwatch_ring_actions"
    const val PREFS_KEY_QUEUE = "queue"
}
