package com.tanmayhatkar.overwatch.widget

import android.content.Context
import android.util.Log
import com.tanmayhatkar.overwatch.BuildConfig
import org.json.JSONArray
import java.net.HttpURLConnection
import java.net.URL
import java.time.Instant
import java.time.LocalDateTime
import java.time.ZoneOffset
import java.time.format.DateTimeParseException

/**
 * CommitmentWidgetRepository.kt — thin HTTP client for the widget's data
 * source.
 *
 * Deliberately kept separate from [CommitmentWidgetWorker] (which owns
 * WorkManager scheduling and Glance-state persistence): this class only
 * knows how to turn "a stored bearer token" into "a list of open
 * commitments." That single responsibility also makes it the one class a
 * future unit test would target in isolation (mocking the token source /
 * HTTP layer) if this project adds Robolectric/instrumentation coverage —
 * not possible to add here given the missing Android toolchain, but the
 * seam is there.
 *
 * No JSON/HTTP library dependency is added for this — org.json and
 * HttpURLConnection are both part of the Android SDK already, which keeps
 * this vertical slice's footprint on shared Gradle files minimal.
 */
class CommitmentWidgetRepository(private val context: Context) {

    /**
     * Fetches the signed-in user's open commitments from the backend.
     *
     * Never throws — every external-call failure path (missing token,
     * DNS/timeout, non-2xx status, malformed body) is caught and converted
     * into a [WidgetFetchResult] so a bad network day can't crash the
     * background worker.
     *
     * @return [WidgetFetchResult.Success] with the raw item list (not yet
     *   sorted/truncated — that's [CommitmentWidgetWorker]'s job),
     *   [WidgetFetchResult.AuthError] if there's no stored token or the
     *   backend returned 401, or [WidgetFetchResult.NetworkError] for
     *   anything else.
     */
    fun fetchOpenCommitments(): WidgetFetchResult {
        val token = readStoredToken() ?: return WidgetFetchResult.AuthError

        var connection: HttpURLConnection? = null
        return try {
            val url = URL(BuildConfig.WIDGET_API_BASE_URL + ENDPOINT_PATH)
            connection = (url.openConnection() as HttpURLConnection).apply {
                requestMethod = "GET"
                setRequestProperty("Authorization", "Bearer $token")
                setRequestProperty("Accept", "application/json")
                connectTimeout = CONNECT_TIMEOUT_MILLIS
                readTimeout = READ_TIMEOUT_MILLIS
            }

            when (val code = connection.responseCode) {
                HttpURLConnection.HTTP_OK -> {
                    val body = connection.inputStream.bufferedReader().use { it.readText() }
                    WidgetFetchResult.Success(parseCommitments(body))
                }
                HttpURLConnection.HTTP_UNAUTHORIZED -> WidgetFetchResult.AuthError
                else -> {
                    Log.w(TAG, "Unexpected response code $code fetching commitments for widget")
                    WidgetFetchResult.NetworkError
                }
            }
        } catch (e: Exception) {
            // Covers UnknownHostException (offline), SocketTimeoutException,
            // JSONException (malformed body), and anything else a widget
            // background job must survive without crashing the app process.
            Log.w(TAG, "Failed to fetch commitments for widget", e)
            WidgetFetchResult.NetworkError
        } finally {
            connection?.disconnect()
        }
    }

    /**
     * Reads the bearer token the native app's login flow stored, or null if
     * the user has never signed in (or signed out).
     *
     * Reads the EXACT SharedPreferences file + key @capacitor/preferences
     * writes to on Android — see frontend/src/lib/native.js (TOKEN_KEY) and
     * node_modules/@capacitor/preferences/android/.../PreferencesConfiguration.java
     * (DEFAULTS.group = "CapacitorStorage"). The plugin stores the token as
     * a raw string under this key with no wrapping/namespacing, and
     * native.js never calls Preferences.configure() to change the group,
     * so this is safe as long as neither side changes independently of the
     * other — flagged as a coupling to watch in ADR-0020.
     */
    private fun readStoredToken(): String? {
        return try {
            context
                .getSharedPreferences(CAPACITOR_PREFS_FILE, Context.MODE_PRIVATE)
                .getString(TOKEN_KEY, null)
        } catch (e: Exception) {
            Log.w(TAG, "Failed to read stored session token", e)
            null
        }
    }

    /** Parses the `GET /commitments` JSON array body into widget rows. */
    private fun parseCommitments(body: String): List<WidgetCommitment> {
        val array = JSONArray(body)
        val items = mutableListOf<WidgetCommitment>()
        for (i in 0 until array.length()) {
            val obj = array.getJSONObject(i)
            val id = obj.optString("id", "")
            val text = obj.optString("text", "")
            if (id.isEmpty() || text.isEmpty()) continue
            val dueAtRaw = obj.optString("due_at", "")
            val dueAtMillis = if (dueAtRaw.isNotEmpty()) parseBackendTimestamp(dueAtRaw) else null
            items.add(WidgetCommitment(id = id, text = text, dueAtEpochMillis = dueAtMillis))
        }
        return items
    }

    /**
     * Parses a backend `due_at` timestamp into epoch millis.
     *
     * The backend (Pydantic's datetime.isoformat()) normally emits an
     * offset-bearing string (e.g. "2026-07-09T14:30:00+00:00"), which
     * java.time.Instant.parse handles directly. Some rows can end up with a
     * naive (offset-less) due_at — see
     * backend/app/services/reminder_scheduler.py, which falls back to UTC
     * for exactly this case — so this mirrors that same UTC fallback rather
     * than dropping the row's time entirely.
     */
    private fun parseBackendTimestamp(raw: String): Long? {
        return try {
            Instant.parse(raw).toEpochMilli()
        } catch (e: DateTimeParseException) {
            try {
                LocalDateTime.parse(raw).toInstant(ZoneOffset.UTC).toEpochMilli()
            } catch (e2: DateTimeParseException) {
                Log.w(TAG, "Unparseable due_at from backend: $raw", e2)
                null
            }
        }
    }

    private companion object {
        const val TAG = "CommitmentWidgetRepo"

        const val CAPACITOR_PREFS_FILE = "CapacitorStorage"
        const val TOKEN_KEY = "ow.session.token"

        const val ENDPOINT_PATH = "/commitments?status_filter=open"
        const val CONNECT_TIMEOUT_MILLIS = 10_000
        const val READ_TIMEOUT_MILLIS = 10_000
    }
}
