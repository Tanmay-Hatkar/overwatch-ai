package com.tanmayhatkar.overwatch

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

/**
 * Tiny persisted queue of ring-alarm actions (Snooze/Done taps) that happened
 * while the Capacitor JS bridge was not alive to receive them live — e.g. the
 * app process was fully killed and the OS launched [RingActivity] straight
 * off the AlarmManager alarm. [RingAlarmPlugin.drainPendingRingActions] reads
 * and clears this on the next JS-side init so nothing is silently lost.
 *
 * Single responsibility: SharedPreferences-backed persistence only. Deciding
 * what an action *means* (mark done, cancel the sibling alarm, ...) is a JS
 * concern, handled in notifications.js.
 */
object RingActionStore {

    private fun prefs(context: Context) =
        context.getSharedPreferences(RingConstants.PREFS_NAME, Context.MODE_PRIVATE)

    /** Append one action to the queue. Best-effort — never throws. */
    fun enqueue(context: Context, id: Int, commitmentId: String?, action: String) {
        try {
            val p = prefs(context)
            val current = JSONArray(p.getString(RingConstants.PREFS_KEY_QUEUE, "[]"))
            val entry = JSONObject()
                .put("id", id)
                .put("commitmentId", commitmentId ?: "")
                .put("action", action)
            current.put(entry)
            p.edit().putString(RingConstants.PREFS_KEY_QUEUE, current.toString()).apply()
        } catch (e: Exception) {
            // Best-effort persistence — a lost action just means the sibling
            // alarm might linger until the next full reconcile from JS.
        }
    }

    /** Read and clear the queue. Returns a JSON array string, "[]" if empty. */
    fun drainAll(context: Context): String {
        return try {
            val p = prefs(context)
            val queued = p.getString(RingConstants.PREFS_KEY_QUEUE, "[]") ?: "[]"
            p.edit().remove(RingConstants.PREFS_KEY_QUEUE).apply()
            queued
        } catch (e: Exception) {
            "[]"
        }
    }
}
