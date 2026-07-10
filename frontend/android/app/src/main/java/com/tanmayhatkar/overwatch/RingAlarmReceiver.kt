package com.tanmayhatkar.overwatch

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat

/**
 * Fires when the AlarmManager alarm scheduled by [RingAlarmPlugin.ring] goes
 * off. Always posts a notification with `setFullScreenIntent(...)` pointing
 * at [RingActivity].
 *
 * On Android 14+ (API 34), if the user has not granted
 * USE_FULL_SCREEN_INTENT, the OS silently downgrades this to a normal
 * heads-up notification instead of auto-launching [RingActivity] — that is
 * documented platform behavior, not something we branch on ourselves. The
 * Snooze/Done actions attached directly to the notification are the
 * fallback path for that case (and for anyone who just prefers to act from
 * the notification shade). See ADR-0019.
 */
class RingAlarmReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        val id = intent.getIntExtra(RingConstants.EXTRA_ID, -1)
        if (id == -1) return
        val commitmentId = intent.getStringExtra(RingConstants.EXTRA_COMMITMENT_ID) ?: ""
        val title = intent.getStringExtra(RingConstants.EXTRA_TITLE) ?: "Overwatch"
        val body = intent.getStringExtra(RingConstants.EXTRA_BODY) ?: ""

        ensureChannel(context)

        val fullScreenIntent = Intent(context, RingActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or
                Intent.FLAG_ACTIVITY_CLEAR_TOP or
                Intent.FLAG_ACTIVITY_SINGLE_TOP or
                Intent.FLAG_ACTIVITY_EXCLUDE_FROM_RECENTS
            putExtra(RingConstants.EXTRA_ID, id)
            putExtra(RingConstants.EXTRA_COMMITMENT_ID, commitmentId)
            putExtra(RingConstants.EXTRA_TITLE, title)
            putExtra(RingConstants.EXTRA_BODY, body)
        }
        val fullScreenPendingIntent = PendingIntent.getActivity(
            context,
            id,
            fullScreenIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )

        val snoozeAction = actionPendingIntent(context, id, commitmentId, "SNOOZE")
        val doneAction = actionPendingIntent(context, id, commitmentId, "DONE")

        val notification = NotificationCompat.Builder(context, RingConstants.CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_lock_idle_alarm)
            .setContentTitle(title)
            .setContentText(body)
            .setCategory(NotificationCompat.CATEGORY_ALARM)
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setFullScreenIntent(fullScreenPendingIntent, true)
            .setContentIntent(fullScreenPendingIntent)
            .addAction(0, "Snooze", snoozeAction)
            .addAction(0, "Done", doneAction)
            .setOngoing(true)
            .setAutoCancel(false)
            .build()

        NotificationManagerCompat.from(context).notify(id, notification)
    }

    /**
     * Distinguishing Snooze from Done (and this commitment's actions from any
     * other commitment's) via the Intent's `data` URI — rather than via
     * request-code arithmetic — is what lets two actions safely coexist on
     * the same notification and never collide across commitments, since
     * PendingIntent/Intent identity includes action+data, not just extras.
     */
    private fun actionPendingIntent(
        context: Context,
        id: Int,
        commitmentId: String,
        action: String,
    ): PendingIntent {
        val intent = Intent(RingConstants.ACTION_RING_BUTTON).apply {
            setClass(context, RingActionReceiver::class.java)
            data = Uri.parse("ringaction://$id/$action")
            putExtra(RingConstants.EXTRA_ID, id)
            putExtra(RingConstants.EXTRA_COMMITMENT_ID, commitmentId)
            putExtra(RingConstants.EXTRA_ACTION, action)
        }
        return PendingIntent.getBroadcast(
            context,
            id,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
    }

    private fun ensureChannel(context: Context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (manager.getNotificationChannel(RingConstants.CHANNEL_ID) != null) return
        val channel = NotificationChannel(
            RingConstants.CHANNEL_ID,
            "Ring alarm (missed reminders)",
            NotificationManager.IMPORTANCE_HIGH,
        ).apply {
            description = "Full-screen ring shown when a reminder was ignored"
            enableVibration(true)
        }
        manager.createNotificationChannel(channel)
    }
}
