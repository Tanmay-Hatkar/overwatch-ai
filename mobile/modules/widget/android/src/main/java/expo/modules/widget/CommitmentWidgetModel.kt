package expo.modules.widget

/**
 * CommitmentWidgetModel.kt — plain data shapes shared between
 * [CommitmentWidgetRepository] (produces them), [CommitmentWidgetWorker]
 * (persists them into Glance state) and [CommitmentWidget] (renders them).
 */

/** One row the widget can render: a commitment's text + when it's due. */
data class WidgetCommitment(
    val id: String,
    val text: String,
    /** Epoch millis, or null if the commitment has no due_at set. */
    val dueAtEpochMillis: Long?,
)

/** Outcome of a [CommitmentWidgetRepository.fetchOpenCommitments] call. */
sealed class WidgetFetchResult {
    /** The backend returned 200 with a (possibly empty) commitment list. */
    data class Success(val items: List<WidgetCommitment>) : WidgetFetchResult()

    /** No config was written yet (never signed in), or the backend returned 401. */
    object AuthError : WidgetFetchResult()

    /** Anything else: offline, timeout, 5xx, malformed response body. */
    object NetworkError : WidgetFetchResult()
}

/**
 * Why the widget is currently showing what it's showing. Persisted (as its
 * [name]) into each widget instance's Glance state by
 * [CommitmentWidgetWorker], read back by [CommitmentWidget].
 */
enum class WidgetStatus {
    OK,
    AUTH_ERROR,
    NETWORK_ERROR,
}
