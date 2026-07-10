package com.tanmayhatkar.overwatch

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import androidx.core.app.NotificationManagerCompat

/**
 * Single funnel for every way a Tier-2 ring can be acknowledged: a Snooze/Done
 * tap on the fallback heads-up notification's action buttons (posted when
 * USE_FULL_SCREEN_INTENT isn't granted, or simply because the user tapped the
 * notification instead of waiting for the full-screen ring), or the same
 * buttons inside [RingActivity] once the full-screen ring is showing.
 *
 * Responsibilities: stop the ring notification, persist the action for the
 * JS bridge (in case the app process was cold-started just to show the ring
 * and no bridge is running yet), and — if the bridge happens to be alive —
 * relay it live so notifications.js's shared handler can react immediately
 * (mark the commitment done, cancel a still-pending sibling alarm, etc).
 *
 * Declared with android:exported="false" in the manifest; every sender in
 * this app scopes its Intent with setPackage(), so this only ever receives
 * from our own app.
 */
class RingActionReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        val id = intent.getIntExtra(RingConstants.EXTRA_ID, -1)
        if (id == -1) return
        val commitmentId = intent.getStringExtra(RingConstants.EXTRA_COMMITMENT_ID)
        val action = intent.getStringExtra(RingConstants.EXTRA_ACTION) ?: return

        // Stop the ring notification (whether it's the full-screen one or the
        // heads-up fallback — both are posted under the same notification id).
        try {
            NotificationManagerCompat.from(context).cancel(id)
        } catch (e: Exception) {
            // best-effort
        }

        // Tell an on-screen RingActivity for this id to stop the audio/vibration
        // and finish (covers the "tapped an action button inside the notification
        // while the ring screen is also showing" case).
        val stop = Intent(RingConstants.ACTION_STOP_RING).setPackage(context.packageName)
        stop.putExtra(RingConstants.EXTRA_ID, id)
        context.sendBroadcast(stop)

        RingActionStore.enqueue(context, id, commitmentId, action)

        val available = Intent(RingConstants.ACTION_RING_AVAILABLE).setPackage(context.packageName)
        available.putExtra(RingConstants.EXTRA_ID, id)
        available.putExtra(RingConstants.EXTRA_COMMITMENT_ID, commitmentId)
        available.putExtra(RingConstants.EXTRA_ACTION, action)
        context.sendBroadcast(available)
    }
}
