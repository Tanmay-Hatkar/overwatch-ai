package com.tanmayhatkar.overwatch.widget

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.text.format.DateUtils
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.datastore.preferences.core.Preferences
import androidx.glance.GlanceId
import androidx.glance.GlanceModifier
import androidx.glance.action.actionStartActivity
import androidx.glance.action.clickable
import androidx.glance.appwidget.GlanceAppWidget
import androidx.glance.appwidget.action.actionStartActivity as actionStartActivityIntent
import androidx.glance.appwidget.provideContent
import androidx.glance.background
import androidx.glance.currentState
import androidx.glance.layout.Column
import androidx.glance.layout.fillMaxSize
import androidx.glance.layout.fillMaxWidth
import androidx.glance.layout.height
import androidx.glance.layout.padding
import androidx.glance.state.PreferencesGlanceStateDefinition
import androidx.glance.text.FontWeight
import androidx.glance.text.Text
import androidx.glance.text.TextStyle
import androidx.glance.unit.ColorProvider
import com.tanmayhatkar.overwatch.MainActivity
import org.json.JSONArray

/**
 * CommitmentWidget.kt — the Glance composable that renders the widget.
 *
 * Pure presentation: reads whatever [CommitmentWidgetWorker] last wrote
 * into this widget instance's Glance state and renders one of four frames
 * — loading (never fetched yet), ok (items or the empty state, optionally
 * with a stale-data badge), auth error ("tap to re-sign in"), or a network
 * error that still shows the last-known-good items with a stale badge.
 * Never touches the network itself.
 *
 * NOTE (manual-verification caveat — see ADR-0020 / final report): several
 * Glance 1.1.x import paths below (in particular
 * `androidx.glance.unit.ColorProvider`) are written from documentation/
 * memory and could not be compile-checked in this environment (no working
 * JDK/Android toolchain). If Android Studio flags an import here, it is a
 * package-path fix only — the composable logic itself does not change.
 */
class CommitmentWidget : GlanceAppWidget() {

    override val stateDefinition = PreferencesGlanceStateDefinition

    override suspend fun provideGlance(context: Context, id: GlanceId) {
        provideContent {
            val prefs = currentState<Preferences>()
            WidgetContent(prefs)
        }
    }

    @Composable
    private fun WidgetContent(prefs: Preferences) {
        val statusName = prefs[CommitmentWidgetWorker.KEY_STATUS]
        val status = statusName?.let { runCatching { WidgetStatus.valueOf(it) }.getOrNull() }
        val itemsJson = prefs[CommitmentWidgetWorker.KEY_ITEMS_JSON]
        val lastFetchMillis = prefs[CommitmentWidgetWorker.KEY_LAST_FETCH_MILLIS]

        Column(
            modifier = GlanceModifier
                .fillMaxSize()
                .background(BACKGROUND_COLOR)
                .padding(12.dp),
        ) {
            Text(
                text = "Overwatch",
                style = TextStyle(
                    color = ColorProvider(ACCENT_COLOR),
                    fontWeight = FontWeight.Bold,
                    fontSize = 13.sp,
                ),
            )
            Spacer()

            when (status) {
                null -> LoadingFrame()
                WidgetStatus.AUTH_ERROR -> AuthErrorFrame()
                WidgetStatus.OK, WidgetStatus.NETWORK_ERROR -> {
                    OkFrame(itemsJson = itemsJson, lastFetchMillis = lastFetchMillis, status = status)
                }
            }
        }
    }

    @Composable
    private fun LoadingFrame() {
        Text(
            text = "Loading…",
            style = TextStyle(color = ColorProvider(SECONDARY_TEXT_COLOR), fontSize = 12.sp),
        )
    }

    @Composable
    private fun AuthErrorFrame() {
        Column(
            modifier = GlanceModifier
                .fillMaxWidth()
                .clickable(actionStartActivity<MainActivity>()),
        ) {
            Text(
                text = "Tap to re-sign in.",
                style = TextStyle(color = ColorProvider(PRIMARY_TEXT_COLOR), fontSize = 13.sp),
            )
        }
    }

    @Composable
    private fun OkFrame(itemsJson: String?, lastFetchMillis: Long?, status: WidgetStatus) {
        val items = parseItems(itemsJson)

        if (items.isEmpty()) {
            Text(
                text = "Nothing pending.",
                style = TextStyle(color = ColorProvider(SECONDARY_TEXT_COLOR), fontSize = 12.sp),
            )
        } else {
            items.forEach { item -> CommitmentRow(item) }
        }

        val showStale = status == WidgetStatus.NETWORK_ERROR || isStale(lastFetchMillis)
        if (showStale) {
            Spacer()
            Text(
                text = formatStaleBadge(lastFetchMillis),
                style = TextStyle(color = ColorProvider(SECONDARY_TEXT_COLOR), fontSize = 10.sp),
            )
        }
    }

    @Composable
    private fun CommitmentRow(item: WidgetCommitment) {
        val timeLabel = item.dueAtEpochMillis?.let { formatDueTime(it) } ?: "No time set"
        Column(
            modifier = GlanceModifier
                .fillMaxWidth()
                .padding(vertical = 4.dp)
                .clickable(actionStartActivityIntent(commitmentDeepLinkIntent(item.id))),
        ) {
            Text(
                text = truncateText(item.text),
                style = TextStyle(
                    color = ColorProvider(PRIMARY_TEXT_COLOR),
                    fontSize = 13.sp,
                    fontWeight = FontWeight.Medium,
                ),
                maxLines = 1,
            )
            Text(
                text = timeLabel,
                style = TextStyle(color = ColorProvider(SECONDARY_TEXT_COLOR), fontSize = 11.sp),
                maxLines = 1,
            )
        }
    }

    @Composable
    private fun Spacer() {
        androidx.glance.layout.Spacer(modifier = GlanceModifier.height(6.dp))
    }

    /** Builds the overwatch://commitment/{id} deep link used by ADR-0020's row-tap contract. */
    private fun commitmentDeepLinkIntent(id: String): Intent =
        Intent(Intent.ACTION_VIEW, Uri.parse("$DEEP_LINK_SCHEME://commitment/$id"))

    private fun parseItems(json: String?): List<WidgetCommitment> {
        if (json.isNullOrEmpty()) return emptyList()
        return try {
            val array = JSONArray(json)
            (0 until array.length()).map { i ->
                val obj = array.getJSONObject(i)
                val dueAt = if (obj.isNull("due_at_millis")) null else obj.getLong("due_at_millis")
                WidgetCommitment(
                    id = obj.getString("id"),
                    text = obj.getString("text"),
                    dueAtEpochMillis = dueAt,
                )
            }
        } catch (e: Exception) {
            emptyList()
        }
    }

    private fun truncateText(text: String): String =
        if (text.length <= MAX_TEXT_LENGTH) text else text.take(MAX_TEXT_LENGTH - 1).trimEnd() + "…"

    private fun formatDueTime(epochMillis: Long): String =
        DateUtils.getRelativeTimeSpanString(
            epochMillis,
            System.currentTimeMillis(),
            DateUtils.MINUTE_IN_MILLIS,
            DateUtils.FORMAT_ABBREV_RELATIVE,
        ).toString()

    private fun isStale(lastFetchMillis: Long?): Boolean {
        if (lastFetchMillis == null) return true
        return System.currentTimeMillis() - lastFetchMillis > STALE_THRESHOLD_MILLIS
    }

    private fun formatStaleBadge(lastFetchMillis: Long?): String {
        if (lastFetchMillis == null) return "Not yet updated"
        val relative = DateUtils.getRelativeTimeSpanString(
            lastFetchMillis,
            System.currentTimeMillis(),
            DateUtils.MINUTE_IN_MILLIS,
            DateUtils.FORMAT_ABBREV_RELATIVE,
        )
        return "Updated $relative"
    }

    private companion object {
        const val DEEP_LINK_SCHEME = "overwatch"
        const val MAX_TEXT_LENGTH = 42

        /** 3x the 30-min refresh interval — one missed cycle is normal, two+ is worth flagging. */
        const val STALE_THRESHOLD_MILLIS = 90 * 60 * 1000L

        val BACKGROUND_COLOR = Color(0xFF1C1B1F)
        val PRIMARY_TEXT_COLOR = Color(0xFFFFFFFF)
        val SECONDARY_TEXT_COLOR = Color(0xFFBBBBBB)
        val ACCENT_COLOR = Color(0xFFFFA552)
    }
}
