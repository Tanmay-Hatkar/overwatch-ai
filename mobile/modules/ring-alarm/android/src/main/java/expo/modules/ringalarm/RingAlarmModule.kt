package expo.modules.ringalarm

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.core.app.NotificationManagerCompat
import expo.modules.kotlin.exception.CodedException
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition

/**
 * RingAlarmModule — Tier 2 "hard to ignore" escalation (ADR-0019).
 *
 * Bridges JS -> AlarmManager (schedule/cancel a full-screen ring for a
 * commitment) and Android -> JS (relay Snooze/Done taps made on the ring
 * screen, or the fallback notification, back into the same shared handler
 * notifications.js already uses for Tier-1 actions).
 *
 * JS-callable functions: ring, cancelRing, checkFullScreenIntentPermission,
 * openFullScreenIntentSettings, drainPendingRingActions.
 * JS-listenable event: "ringAction" -> { id, commitmentId, action }.
 */
private class MissingContextException :
    CodedException("Android context is unavailable — module not attached to an activity")

class RingAlarmModule : Module() {

    /** Relays ring-button taps to JS live, while this module is alive. */
    private val liveActionReceiver = object : BroadcastReceiver() {
        override fun onReceive(receiverContext: Context, intent: Intent) {
            sendEvent(
                "ringAction",
                mapOf(
                    "id" to intent.getIntExtra(RingConstants.EXTRA_ID, 0),
                    "commitmentId" to (intent.getStringExtra(RingConstants.EXTRA_COMMITMENT_ID) ?: ""),
                    "action" to (intent.getStringExtra(RingConstants.EXTRA_ACTION) ?: ""),
                ),
            )
        }
    }

    override fun definition() = ModuleDefinition {
        Name("RingAlarm")

        Events("ringAction")

        OnCreate {
            val context = appContext.reactContext ?: return@OnCreate
            val filter = IntentFilter(RingConstants.ACTION_RING_AVAILABLE)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                context.registerReceiver(liveActionReceiver, filter, Context.RECEIVER_NOT_EXPORTED)
            } else {
                @Suppress("UnspecifiedRegisterReceiverFlag")
                context.registerReceiver(liveActionReceiver, filter)
            }
        }

        OnDestroy {
            try {
                appContext.reactContext?.unregisterReceiver(liveActionReceiver)
            } catch (e: Exception) {
                // not registered / already torn down — fine
            }
        }

        AsyncFunction("ring") { id: Int, commitmentId: String, title: String, body: String, atMillis: Double ->
            val context = appContext.reactContext ?: throw MissingContextException()
            val alarmManager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
            // FLAG_UPDATE_CURRENT means a re-schedule (e.g. next reconcileRingAlarms
            // pass with fresher commitment text) replaces the extras on the
            // existing PendingIntent rather than needing a lookup-then-branch.
            val operation = buildAlarmOperation(context, id, commitmentId, title, body)

            val launchIntent = context.packageManager.getLaunchIntentForPackage(context.packageName)
                ?: Intent(Intent.ACTION_MAIN).setPackage(context.packageName)
            val showOperation = PendingIntent.getActivity(
                context,
                id,
                launchIntent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            )

            // setAlarmClock (rather than setExactAndAllowWhileIdle): more
            // Doze-resistant, and shows the persistent status-bar alarm icon —
            // deliberate transparency that this app has a ring pending. See
            // ADR-0019.
            alarmManager.setAlarmClock(
                AlarmManager.AlarmClockInfo(atMillis.toLong(), showOperation),
                operation,
            )
        }

        AsyncFunction("cancelRing") { id: Int ->
            val context = appContext.reactContext ?: throw MissingContextException()
            val alarmManager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
            val operation = buildAlarmOperation(context, id, "", "", "")
            alarmManager.cancel(operation)
            operation.cancel()

            // In case the alarm already fired (notification posted / ring
            // screen already launched) before this cancel arrived.
            NotificationManagerCompat.from(context).cancel(id)
            val stop = Intent(RingConstants.ACTION_STOP_RING).setPackage(context.packageName)
            stop.putExtra(RingConstants.EXTRA_ID, id)
            context.sendBroadcast(stop)
        }

        AsyncFunction("checkFullScreenIntentPermission") {
            val context = appContext.reactContext
            if (context != null && Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
                NotificationManagerCompat.from(context).canUseFullScreenIntent()
            } else {
                true // the permission concept doesn't exist before API 34
            }
        }

        AsyncFunction("openFullScreenIntentSettings") {
            val context = appContext.reactContext
            if (context != null && Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
                val intent = Intent(Settings.ACTION_MANAGE_APP_USE_FULL_SCREEN_INTENT).apply {
                    data = Uri.parse("package:${context.packageName}")
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK
                }
                context.startActivity(intent)
            }
        }

        /** Drains actions queued by RingActionReceiver while no bridge was alive to receive them live. */
        AsyncFunction("drainPendingRingActions") {
            val context = appContext.reactContext ?: return@AsyncFunction emptyList<Map<String, Any>>()
            RingActionStore.drainAll(context)
        }
    }

    private fun buildAlarmOperation(
        context: Context,
        id: Int,
        commitmentId: String,
        title: String,
        body: String,
    ): PendingIntent {
        val intent = Intent(context, RingAlarmReceiver::class.java).apply {
            action = RingConstants.ACTION_ALARM_FIRED
            putExtra(RingConstants.EXTRA_ID, id)
            putExtra(RingConstants.EXTRA_COMMITMENT_ID, commitmentId)
            putExtra(RingConstants.EXTRA_TITLE, title)
            putExtra(RingConstants.EXTRA_BODY, body)
        }
        return PendingIntent.getBroadcast(
            context,
            id,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
    }
}
