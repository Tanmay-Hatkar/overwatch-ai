package com.tanmayhatkar.overwatch.widget

import android.content.Context
import android.util.Log
import androidx.datastore.preferences.core.longPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.glance.appwidget.GlanceAppWidgetManager
import androidx.glance.appwidget.state.updateAppWidgetState
import androidx.glance.state.PreferencesGlanceStateDefinition
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject

/**
 * CommitmentWidgetWorker.kt — the periodic background job that refreshes
 * the widget's data.
 *
 * Runs on a WorkManager PeriodicWorkRequest (~30 min, network-constrained —
 * see CommitmentWidgetReceiver.enqueuePeriodicRefresh). Each run: fetch via
 * [CommitmentWidgetRepository], keep the 3 nearest-due items, and persist
 * them into every placed widget instance's Glance state so the widget
 * always has last-known-good data to render even when a given run fails
 * (offline, backend down, expired token).
 */
class CommitmentWidgetWorker(
    context: Context,
    params: WorkerParameters,
) : CoroutineWorker(context, params) {

    private val repository = CommitmentWidgetRepository(applicationContext)

    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        val fetchResult = try {
            repository.fetchOpenCommitments()
        } catch (e: Exception) {
            // Belt-and-suspenders: the repository already catches its own
            // external-call failures, but doWork() must never throw — an
            // uncaught exception here would crash the app process if it
            // happens to be in the foreground when WorkManager runs this.
            Log.w(TAG, "Unexpected error fetching widget data", e)
            WidgetFetchResult.NetworkError
        }

        val manager = GlanceAppWidgetManager(applicationContext)
        val glanceIds = manager.getGlanceIds(CommitmentWidget::class.java)
        if (glanceIds.isEmpty()) {
            // No widget instance currently placed — nothing to update.
            // Shouldn't normally happen (the Receiver cancels this job in
            // onDisabled) but a scheduled retry can race a removal.
            return@withContext Result.success()
        }

        for (glanceId in glanceIds) {
            updateAppWidgetState(applicationContext, PreferencesGlanceStateDefinition, glanceId) { prefs ->
                val mutablePrefs = prefs.toMutablePreferences()
                when (fetchResult) {
                    is WidgetFetchResult.Success -> {
                        val nearest = fetchResult.items
                            .sortedWith(compareBy<WidgetCommitment, Long?>(nullsLast()) { it.dueAtEpochMillis })
                            .take(MAX_ITEMS)
                        mutablePrefs[KEY_STATUS] = WidgetStatus.OK.name
                        mutablePrefs[KEY_ITEMS_JSON] = serializeItems(nearest)
                        mutablePrefs[KEY_LAST_FETCH_MILLIS] = System.currentTimeMillis()
                    }
                    WidgetFetchResult.AuthError -> {
                        mutablePrefs[KEY_STATUS] = WidgetStatus.AUTH_ERROR.name
                        // Deliberately leave KEY_ITEMS_JSON / KEY_LAST_FETCH_MILLIS
                        // untouched — CommitmentWidget renders the sign-in
                        // prompt whenever status is AUTH_ERROR regardless of
                        // whatever stale items are still cached underneath.
                    }
                    WidgetFetchResult.NetworkError -> {
                        mutablePrefs[KEY_STATUS] = WidgetStatus.NETWORK_ERROR.name
                        // Leave items/timestamp exactly as they were on the
                        // last successful fetch — "always render
                        // last-known-good data" per ADR-0020.
                    }
                }
                mutablePrefs
            }
            CommitmentWidget().update(applicationContext, glanceId)
        }

        Result.success()
    }

    private fun serializeItems(items: List<WidgetCommitment>): String {
        val array = JSONArray()
        items.forEach { item ->
            val obj = JSONObject()
            obj.put("id", item.id)
            obj.put("text", item.text)
            obj.put("due_at_millis", item.dueAtEpochMillis ?: JSONObject.NULL)
            array.put(obj)
        }
        return array.toString()
    }

    companion object {
        private const val TAG = "CommitmentWidgetWorker"

        /** How many nearest-due items to keep — matches the widget's row count. */
        const val MAX_ITEMS = 3

        /** WorkManager unique-work name, shared by enqueue (Receiver) and cancel (Receiver). */
        const val UNIQUE_WORK_NAME = "commitment_widget_refresh"

        val KEY_STATUS = stringPreferencesKey("widget_status")
        val KEY_ITEMS_JSON = stringPreferencesKey("widget_items_json")
        val KEY_LAST_FETCH_MILLIS = longPreferencesKey("widget_last_fetch_millis")
    }
}
