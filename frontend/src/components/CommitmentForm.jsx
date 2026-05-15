import { useState } from 'react'
import { createCommitment } from '../api'

/**
 * Form for adding a new commitment.
 *
 * Local state: input text, submitting flag, error message.
 * Calls onCreated() after a successful submit so the parent can refresh.
 */
export default function CommitmentForm({ onCreated }) {
  const [text, setText] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  async function handleSubmit(event) {
    event.preventDefault()
    const trimmed = text.trim()
    if (!trimmed) return

    setSubmitting(true)
    setError(null)
    try {
      await createCommitment(trimmed)
      setText('')
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
      {error && <p className="text-red-500 text-sm mt-2">{error}</p>}
    </form>
  )
}
