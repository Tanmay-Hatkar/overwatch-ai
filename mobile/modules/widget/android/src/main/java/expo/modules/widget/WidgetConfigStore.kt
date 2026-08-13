package expo.modules.widget

import android.content.Context

/**
 * Tiny private SharedPreferences-backed store for what the widget's
 * background worker needs to call the backend: the API base URL and the
 * signed-in user's bearer token. Written by [WidgetModule] (called from
 * lib/widget.js alongside auth.js's SecureStore writes), read by
 * [CommitmentWidgetRepository].
 *
 * Deliberately a plain (unencrypted) SharedPreferences file rather than
 * reverse-engineering expo-secure-store's EncryptedSharedPreferences
 * internals from a separate module -- this file is still sandboxed to the
 * app's own UID like any other private app storage, the same protection
 * SecureStore ultimately relies on against other apps. The gap is only
 * extra defense-in-depth against device-level compromise / backup
 * extraction, not a materially different threat model for a widget that
 * already has to carry this same token into a background worker process.
 */
object WidgetConfigStore {

    data class Config(val baseUrl: String, val token: String)

    private const val PREFS_NAME = "overwatch_widget_config"
    private const val KEY_BASE_URL = "baseUrl"
    private const val KEY_TOKEN = "token"

    private fun prefs(context: Context) =
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    fun write(context: Context, baseUrl: String, token: String) {
        prefs(context).edit()
            .putString(KEY_BASE_URL, baseUrl)
            .putString(KEY_TOKEN, token)
            .apply()
    }

    fun clear(context: Context) {
        prefs(context).edit().clear().apply()
    }

    /** Null if never configured (never signed in), or cleared since (signed out). */
    fun read(context: Context): Config? {
        val p = prefs(context)
        val baseUrl = p.getString(KEY_BASE_URL, null) ?: return null
        val token = p.getString(KEY_TOKEN, null) ?: return null
        return Config(baseUrl, token)
    }
}
