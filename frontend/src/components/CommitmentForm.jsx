import { useState } from 'react'
import { toast } from 'sonner'
import { createCommitment, parseCommitment } from '../api'

const MODE_STRUCTURED = 'structured'
const MODE_NATURAL = 'natural'

/**
 * Form for adding a new commitment.
 *
 * Two modes:
 *   - Structured: text input + optional datetime picker. Sends to POST /commitments.
 *   - Natural Language: single text input. Server uses LLM to extract
 *     text + due_at. Sends to POST /commitments/parse.
 *
 * Errors surface as toasts (via sonner). Local error state is gone —
 * the toast container handles all user-visible feedback.
 */
export default function CommitmentForm({ onCreated }) {
  const [mode, setMode] = useState(MODE_STRUCTURED)
  const [text, setText] = useState('')
  const [dueAt, setDueAt] = useState('')
  const [showDuePicker, setShowDuePicker] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  function resetForm() {
    setText('')
    setDueAt('')
    setShowDuePicker(false)
  }

  async function handleSubmit(event) {
    event.preventDefault()
    const trimmed = text.trim()
    if (!trimmed) return

    setSubmitting(true)
    try {
      if (mode === MODE_NATURAL) {
        const result = await parseCommitment(trimmed)
        toast.success(`Added: ${result.text}`)
      } else {
        const dueAtIso = dueAt ? new Date(dueAt).toISOString() : null
        const result = await createCommitment(trimmed, dueAtIso)
        toast.success(`Added: ${result.text}`)
      }
      resetForm()
      onCreated()
    } catch (err) {
      const msg =
        mode === MODE_NATURAL && err.message.includes('503')
          ? "Couldn't parse that. Try rephrasing or switch to Structured mode."
          : err.message || 'Something went wrong.'
      toast.error(msg)
    } finally {
      setSubmitting(false)
    }
  }

  const isNL = mode === MODE_NATURAL

  return (
    <form onSubmit={handleSubmit} className="mb-10">
      {/* Mode toggle */}
      <div className="flex gap-1 mb-3">
        <ModeButton
          active={mode === MODE_STRUCTURED}
          onClick={() => setMode(MODE_STRUCTURED)}
        >
          Structured
        </ModeButton>
        <ModeButton
          active={mode === MODE_NATURAL}
          onClick={() => setMode(MODE_NATURAL)}
        >
          Natural Language
        </ModeButton>
      </div>

      {/* Primary input row */}
      <div className="flex gap-2 flex-wrap">
        <input
          type="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={
            isNL
              ? 'Try: "remind me to call mom tomorrow at 3pm"'
              : "What did you say you'd do?"
          }
          disabled={submitting}
          autoFocus
          className="flex-1 min-w-[200px] px-4 py-3 bg-[#1a1a1a] border border-[#2a2a2a] rounded-lg text-[#f5f5f5] text-sm placeholder:text-zinc-600 focus:outline-none focus:border-orange-500 transition-colors"
        />
        <button
          type="submit"
          disabled={submitting || !text.trim()}
          className="px-6 py-3 bg-orange-500 hover:bg-orange-600 disabled:bg-[#2a2a2a] disabled:text-zinc-600 disabled:cursor-not-allowed text-black font-semibold rounded-lg text-sm transition-colors"
        >
          {submitting ? (isNL ? 'Parsing…' : 'Adding…') : (isNL ? 'Parse' : 'Add')}
        </button>
      </div>

      {/* Structured: optional due-date picker */}
      {!isNL && (
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
      )}

      {isNL && (
        <p className="text-xs text-zinc-600 mt-2">
          AI extracts the action and any time/date you mention.
        </p>
      )}
    </form>
  )
}

function ModeButton({ active, onClick, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`px-3 py-1 text-[11px] font-medium rounded-md transition-colors ${
        active
          ? 'bg-orange-500 text-black'
          : 'bg-[#1a1a1a] border border-[#2a2a2a] text-zinc-400 hover:text-white hover:border-[#3a3a3a]'
      }`}
    >
      {children}
    </button>
  )
}
