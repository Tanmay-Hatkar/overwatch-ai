import { useState } from 'react'
import { createCommitment } from '../api'

/**
 * Form for adding a new commitment.
 *
 * Local state: text input, optional due date/time, submitting flag, error.
 * Calls onCreated() after a successful submit so the parent can refresh.
 *
 * `due_at` is an HTML5 datetime-local input (no timezone). On submit we
 * convert to ISO 8601 string. Empty string means no due date (null).
 */
export default function CommitmentForm({ onCreated }) {
  const [text, setText] = useState('')
  const [dueAt, setDueAt] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  async function handleSubmit(event) {
    event.preventDefault()
    const trimmed = text.trim()
    if (!trimmed) return

    setSubmitting(true)
    setError(null)
    try {
      // datetime-local input format: "YYYY-MM-DDTHH:MM" (no seconds, no tz).
      // Convert to ISO string with timezone. Empty = null.
      const dueAtIso = dueAt ? new Date(dueAt).toISOString() : null
      await createCommitment(trimmed, dueAtIso)
      setText('')
      setDueAt('')
      onCreated()
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="mb-10 space-y-2">
      <div className="flex gap-2 flex-wrap">
        <input
          type="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="What did you say you'd do?"
          disabled={submitting}
          autoFocus
          className="flex-1 min-w-[200px] px-4 py-3 bg-[#1a1a1a] border border-[#2a2a2a] rounded-lg text-[#f5f5f5] text-sm placeholder:text-zinc-600 focus:outline-none focus:border-orange-500 transition-colors"
        />
        <button
          type="submit"
          disabled={submitting || !text.trim()}
          className="px-6 py-3 bg-orange-500 hover:bg-orange-600 disabled:bg-[#2a2a2a] disabled:text-zinc-600 disabled:cursor-not-allowed text-black font-semibold rounded-lg text-sm transition-colors"
        >
          {submitting ? 'Adding…' : 'Add'}
        </button>
      </div>

      <div className="flex items-center gap-2">
        <label htmlFor="due-at" className="text-xs uppercase tracking-widest text-zinc-600 shrink-0">
          Due (optional)
        </label>
        <input
          id="due-at"
          type="datetime-local"
          value={dueAt}
          onChange={(e) => setDueAt(e.target.value)}
          disabled={submitting}
          className="flex-1 px-3 py-2 bg-[#1a1a1a] border border-[#2a2a2a] rounded-lg text-[#f5f5f5] text-sm focus:outline-none focus:border-orange-500 transition-colors [color-scheme:dark]"
        />
        {dueAt && (
          <button
            type="button"
            onClick={() => setDueAt('')}
            className="text-zinc-600 hover:text-red-500 text-sm transition-colors px-2"
          >
            clear
          </button>
        )}
      </div>

      {error && <p className="text-red-500 text-sm">{error}</p>}
    </form>
  )
}
