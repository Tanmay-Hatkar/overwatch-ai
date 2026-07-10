package com.tanmayhatkar.overwatch.widget

import android.content.Context
import androidx.glance.appwidget.GlanceAppWidget
import androidx.glance.appwidget.GlanceAppWidgetReceiver
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import java.util.concurrent.TimeUnit

/**
 * CommitmentWidgetReceiver.kt — the AppWidgetProvider entry point Android
 * calls into (declared as a `<receiver>` in AndroidManifest.xml, pointing
 * at res/xml/commitment_widget_info.xml).
 *
 * Single responsibility: own the widget's background-refresh lifecycle.
 * [onEnabled] fires once, when the FIRST instance of this widget is placed
 * on a home screen (or pinned to a lock screen — same mechanism, see
 * ADR-0020); [onDisabled] fires once, when the LAST instance is removed.
 * That makes them the right place to start/stop the periodic WorkManager
 * job — no point polling the backend when no widget is on screen to show
 * the result.
 */
class CommitmentWidgetReceiver : GlanceAppWidgetReceiver() {

    override val glanceAppWidget: GlanceAppWidget = CommitmentWidget()

    override fun onEnabled(context: Context) {
        super.onEnabled(context)
        enqueuePeriodicRefresh(context)
    }

    override fun onDisabled(context: Context) {
        WorkManager.getInstance(context).cancelUniqueWork(CommitmentWidgetWorker.UNIQUE_WORK_NAME)
        super.onDisabled(context)
    }

    /**
     * Enqueues the recurring background fetch, 30 minutes apart,
     * constrained to a connected network.
     *
     * 30 minutes is the practical floor for periodic background work on
     * Android — both AppWidgetManager.updatePeriodMillis (see
     * commitment_widget_info.xml) and PeriodicWorkRequest silently clamp
     * any shorter interval up, so there's no fresher option here without
     * switching to a push-triggered refresh (rejected for v1 — see
     * ADR-0020: it would need a second, native FCM push integration
     * alongside the existing browser-only Web Push/VAPID system).
     *
     * KEEP policy: if a widget is removed and re-added (or the app process
     * restarts and onEnabled fires again for an already-placed widget),
     * this does not reset the existing schedule's timer.
     */
    private fun enqueuePeriodicRefresh(context: Context) {
        val constraints = Constraints.Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED)
            .build()

        val request = PeriodicWorkRequestBuilder<CommitmentWidgetWorker>(30, TimeUnit.MINUTES)
            .setConstraints(constraints)
            .build()

        WorkManager.getInstance(context).enqueueUniquePeriodicWork(
            CommitmentWidgetWorker.UNIQUE_WORK_NAME,
            ExistingPeriodicWorkPolicy.KEEP,
            request,
        )
    }
}
