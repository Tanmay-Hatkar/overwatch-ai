package com.tanmayhatkar.overwatch

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
import com.getcapacitor.JSObject
import com.getcapacitor.Plugin
import com.getcapacitor.PluginCall
import com.getcapacitor.PluginMethod
import com.getcapacitor.annotation.CapacitorPlugin
import org.json.JSONArray

/**
 * RingAlarmPlugin — Tier 2 "hard to ignore" escalation (ADR-0019).
 *
 * Bridges JS -> AlarmManager (schedule/cancel a full-screen ring for a
 * commitment) and Android -> JS (relay Snooze/Done taps made on the ring
 * screen, or the fallback notification, back into the same shared handler
 * notifications.js already uses for Tier-1 actions).
 *
 * JS-callable methods: ring, cancelRing, checkFullScreenIntentPermission,
 * openFullScreenIntentSettings, drainPendingRingActions.
 * JS-listenable event: "ringAction" -> { id, commitmentId, action }.
 */
@CapacitorPlugin(name = "RingAlarm")
class RingAlarmPlugin : Plugin() {

    /** Relays ring-button taps to JS live, while this plugin/bridge is alive. */
    private val liveActionReceiver = object : BroadcastReceiver() {
        override fun onReceive(receiverContext: Context, intent: Intent) {
            val payload = JSObject()
            payload.put("id", intent.getIntExtra(RingConstants.EXTRA_ID, 0))
            payload.put(
                "commitmentId",
                intent.getStringExtra(RingConstants.EXTRA_COMMITMENT_ID) ?: "",
            )
            payload.put("action", intent.getStringExtra(RingConstants.EXTRA_ACTION) ?: "")
            notifyListeners("ringAction", payload)
        }
    }

    override fun load() {
        super.load()
        val filter = IntentFilter(RingConstants.ACTION_RING_AVAILABLE)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            context.registerReceiver(liveActionReceiver, filter, Context.RECEIVER_NOT_EXPORTED)
        } else {
            @Suppress("UnspecifiedRegisterReceiverFlag")
            context.registerReceiver(liveActionReceiver, filter)
        }
    }

    override fun handleOnDestroy() {
        try {
            context.unregisterReceiver(liveActionReceiver)
        } catch (e: Exception) {
            // not registered / already torn down — fine
        }
        super.handleOnDestroy()
    }

    /** ring({ id: Int, commitmentId: String, title: String, body: String, at: Double(epoch ms) }) */
    @PluginMethod
    fun ring(call: PluginCall) {
        val id = call.getInt("id")
        val atMillis = call.getDouble("at")
        if (id == null || atMillis == null) {
            call.reject("id and at are required")
            return
        }
        val commitmentId = call.getString("commitmentId", "") ?: ""
        val title = call.getString("title", "Overwatch") ?: "Overwatch"
        val body = call.getString("body", "") ?: ""

        try {
            val alarmManager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
            // FLAG_UPDATE_CURRENT means a re-schedule (e.g. next reconcileRingAlarms
            // pass with fresher commitment text) replaces the extras on the
            // existing PendingIntent rather than needing a lookup-then-branch.
            val operation = buildAlarmOperation(context, id, commitmentId, title, body)

            val launchIntent = context.packageManager.getLaunchIntentForPackage(context.packageName)
                ?: Intent(context, MainActivity::class.java)
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
            call.resolve()
        } catch (e: Exception) {
            call.reject("Failed to schedule ring alarm: ${e.message}", e)
        }
    }

    /** cancelRing({ id: Int }) */
    @PluginMethod
    fun cancelRing(call: PluginCall) {
        val id = call.getInt("id")
        if (id == null) {
            call.reject("id is required")
            return
        }
        try {
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

            call.resolve()
        } catch (e: Exception) {
            call.reject("Failed to cancel ring alarm: ${e.message}", e)
        }
    }

    @PluginMethod
    fun checkFullScreenIntentPermission(call: PluginCall) {
        val granted = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            NotificationManagerCompat.from(context).canUseFullScreenIntent()
        } else {
            true // the permission concept doesn't exist before API 34
        }
        val result = JSObject()
        result.put("granted", granted)
        call.resolve(result)
    }

    @PluginMethod
    fun openFullScreenIntentSettings(call: PluginCall) {
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
                val intent = Intent(Settings.ACTION_MANAGE_APP_USE_FULL_SCREEN_INTENT).apply {
                    data = Uri.parse("package:${context.packageName}")
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK
                }
                context.startActivity(intent)
            }
            call.resolve()
        } catch (e: Exception) {
            call.reject("Could not open full-screen-intent settings: ${e.message}", e)
        }
    }

    /** Drains actions queued by RingActionReceiver while no bridge was alive to receive them live. */
    @PluginMethod
    fun drainPendingRingActions(call: PluginCall) {
        try {
            val json = RingActionStore.drainAll(context)
            val result = JSObject()
            result.put("actions", JSONArray(json))
            call.resolve(result)
        } catch (e: Exception) {
            call.reject("Failed to read pending ring actions: ${e.message}", e)
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
