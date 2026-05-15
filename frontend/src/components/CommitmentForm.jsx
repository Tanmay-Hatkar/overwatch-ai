import { useState } from 'react'
import { createCommitment } from '../api'

/**
 * Form for adding a new commitment.
 *
 * Layout: the text input is the primary focus. A secondary "+ add due date"
 * toggle reveals the datetime picker only when the user wants one. Keeps the
 * default form clean while still exposing optional due dates.
 *
 * `due_at` uses HTML5 datetime-local (no timezone in the input value). On
 * submit we convert to ISO 8601 with the browser's timezone applied.
 */
export default function CommitmentForm({ onCreated }) {
  const [text, setText] = useState('')
  const [dueAt, setDueAt] = useState('')
  const [showDuePicker, setShowDuePicker] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  async function handleSubmit(event) {
    event.preventDefault()
    const trimmed = text.trim()
    if (!trimmed) return

    setSubmitting(true)
    setError(null)
    try {
      // datetime-local format: "YYYY-MM-DDTHH:MM" (no seconds, no tz).
      // new Date() parses in the browser's local zone; toISOString() then
      // emits UTC. Empty string = null (no due date).
      const dueAtIso = dueAt ? new Date(dueAt).toISOString() : null
      await createCommitment(trimmed, dueAtIso)
      setText('')
      setDueAt('')
      setShowDuePicker(false)
      onCreated()
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="mb-10">
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

      {/* Secondary row: only shown when user wants to add a due date.
          Keeps the default form visually focused on the primary text input. */}
      <div className="mt-2">
        {!showDuePicker ? (
          <button
            type="button"
            onClick={() => setShowDuePicker(true)}
            className="text-xs text-zinc-500 hover:text-orange-500 transition-colors"
          >
            + add due date
          </button>
        ) : (
          <div className="flex items-center gap-2">
            <input
              type="datetime-local"
              value={dueAt}
              onChange={(e) => setDueAt(e.target.value)}
              disabled={submitting}
              className="px-3 py-1.5 bg-[#1a1a1a] border border-[#2a2a2a] rounded-md text-[#f5f5f5] text-xs focus:outline-none focus:border-orange-500 transition-colors [color-scheme:dark]"
            />
            <button
              type="button"
              onClick={() => {
                setDueAt('')
                setShowDuePicker(false)
              }}
              className="text-xs text-zinc-500 hover:text-red-500 transition-colors"
            >
              remove
            </button>
          </div>
        )}
      </div>

      {error && <p className="text-red-500 text-sm mt-2">{error}</p>}
    </form>
  )
}
