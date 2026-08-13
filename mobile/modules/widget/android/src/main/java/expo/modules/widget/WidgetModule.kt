package expo.modules.widget

import android.content.Context
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition

/**
 * WidgetModule — Home-screen widget (ADR-0020).
 *
 * The Glance widget (CommitmentWidget/CommitmentWidgetReceiver/
 * CommitmentWidgetWorker) runs entirely independently of JS once placed —
 * this module's only job is the two things JS needs to hand off: what to
 * authenticate with ([configure]/[clear], mirroring auth.js's SecureStore
 * writes) and an immediate refresh right after sign-in rather than waiting
 * for the first 30-minute cycle ([refreshNow]).
 */
class WidgetModule : Module() {
    override fun definition() = ModuleDefinition {
        Name("Widget")

        AsyncFunction("configure") { baseUrl: String, token: String ->
            val context = appContext.reactContext
            if (context != null) {
                WidgetConfigStore.write(context, baseUrl, token)
                enqueueImmediateRefresh(context)
            }
        }

        AsyncFunction("clear") {
            val context = appContext.reactContext
            if (context != null) {
                WidgetConfigStore.clear(context)
            }
        }

        AsyncFunction("refreshNow") {
            val context = appContext.reactContext
            if (context != null) {
                enqueueImmediateRefresh(context)
            }
        }
    }

    private fun enqueueImmediateRefresh(context: Context) {
        val request = OneTimeWorkRequestBuilder<CommitmentWidgetWorker>().build()
        WorkManager.getInstance(context).enqueue(request)
    }
}
