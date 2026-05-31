import { useState } from 'react'
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
 * The mode is selected by a toggle at the top of the form. Local state
 * for input + flags is shared between modes (text is the input for both).
 */
export default function CommitmentForm({ onCreated }) {
  const [mode, setMode] = useState(MODE_STRUCTURED)
  const [text, setText] = useState('')
  const [dueAt, setDueAt] = useState('')
  const [showDuePicker, setShowDuePicker] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  function resetForm() {
    setText('')
    setDueAt('')
    setShowDuePicker(false)
    setError(null)
  }

  async function handleSubmit(event) {
    event.preventDefault()
    const trimmed = text.trim()
    if (!trimmed) return

    setSubmitting(true)
    setError(null)
    try {
      if (mode === MODE_NATURAL) {
        await parseCommitment(trimmed)
      } else {
        const dueAtIso = dueAt ? new Date(dueAt).toISOString() : null
        await createCommitment(trimmed, dueAtIso)
      }
      resetForm()
      onCreated()
    } catch (err) {
      setError(formatError(err, mode))
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
          onClick={() => {
            setMode(MODE_STRUCTURED)
            setError(null)
          }}
        >
          Structured
        </ModeButton>
        <ModeButton
          active={mode === MODE_NATURAL}
          onClick={() => {
            setMode(MODE_NATURAL)
            setError(null)
          }}
        >
          Natural Language
        </ModeButton>
      </div>

      {/* Primary input row — shared between both modes */}
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

      {/* Structured mode: optional due-date picker */}
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

      {/* Natural-language mode: hint text */}
      {isNL && (
        <p className="text-xs text-zinc-600 mt-2">
          AI extracts the action and any time/date you mention.
        </p>
      )}

      {error && <p className="text-red-500 text-sm mt-2">{error}</p>}
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

/**
 * Translate fetch errors into user-readable messages.
 * 503 from /parse means the LLM is unavailable or returned bad output.
 */
function formatError(err, mode) {
  const msg = err.message || 'Something went wrong.'
  if (mode === MODE_NATURAL && msg.includes('503')) {
    return "Couldn't parse that. Try rephrasing or switch to Structured mode."
  }
  return msg
}
