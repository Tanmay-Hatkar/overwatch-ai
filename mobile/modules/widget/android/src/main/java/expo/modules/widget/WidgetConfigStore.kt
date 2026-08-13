package expo.modules.widget

import android.content.Context
import org.json.JSONObject
import java.io.File

/**
 * Tiny private store for what the widget's background worker needs to call
 * the backend: the API base URL and the signed-in user's bearer token.
 * Written by [WidgetModule] (called from lib/widget.js alongside auth.js's
 * SecureStore writes), read by [CommitmentWidgetRepository].
 *
 * Backed by a plain JSON file under [Context.getNoBackupFilesDir], not
 * SharedPreferences. That distinction matters: SharedPreferences files live
 * under a directory Android includes in Auto Backup (and device-to-device
 * transfer) by default, so a plain SharedPreferences file here would have
 * shipped this bearer token in plaintext into the user's cloud backup --
 * this app's manifest already carries expo-secure-store's backup-exclusion
 * rules, but those only exclude SecureStore's own file, not a second one a
 * different module invents. `noBackupFilesDir` is the standard Android
 * mechanism for exactly this case (data that must survive process death but
 * must never be backed up) and needs no manifest/backup-rules involvement
 * at all -- the OS excludes the whole directory unconditionally.
 */
object WidgetConfigStore {

    data class Config(val baseUrl: String, val token: String)

    private const val FILE_NAME = "overwatch_widget_config.json"
    private const val KEY_BASE_URL = "baseUrl"
    private const val KEY_TOKEN = "token"

    private fun configFile(context: Context) = File(context.noBackupFilesDir, FILE_NAME)

    /** Best-effort -- a failed write just leaves the widget on its previous (or no) config. */
    fun write(context: Context, baseUrl: String, token: String) {
        try {
            val json = JSONObject().put(KEY_BASE_URL, baseUrl).put(KEY_TOKEN, token)
            configFile(context).writeText(json.toString())
        } catch (e: Exception) {
            // best-effort
        }
    }

    fun clear(context: Context) {
        try {
            configFile(context).delete()
        } catch (e: Exception) {
            // best-effort
        }
    }

    /** Null if never configured (never signed in), or cleared since (signed out). */
    fun read(context: Context): Config? {
        val file = configFile(context)
        if (!file.exists()) return null
        return try {
            val json = JSONObject(file.readText())
            val baseUrl = json.optString(KEY_BASE_URL, "").ifEmpty { null } ?: return null
            val token = json.optString(KEY_TOKEN, "").ifEmpty { null } ?: return null
            Config(baseUrl, token)
        } catch (e: Exception) {
            null
        }
    }
}
