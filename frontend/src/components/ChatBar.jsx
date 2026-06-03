import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { sendChat } from '../api'

const HISTORY_KEY = 'overwatch.chat.history'
const MAX_HISTORY_TURNS = 20      // cap conversation memory length
const HISTORY_FOR_PROMPT = 10     // how many recent turns to send to backend

function loadHistory() {
  try {
    const raw = localStorage.getItem(HISTORY_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function saveHistory(turns) {
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(turns))
  } catch {
    // localStorage full / disabled — ignore
  }
}

/**
 * ChatBar — fixed-bottom conversational input + recent message history.
 *
 * Behavior:
 *   - User types a message, presses Enter or clicks Send
 *   - Frontend POSTs to /chat with the message + last ~10 turns of history
 *   - Backend classifies intent, may create a commitment, returns a reply
 *   - Reply renders above the input
 *   - If a commitment was created, the parent's onAction callback fires
 *     so the list/calendar/briefing refresh
 *
 * History persists across reloads via localStorage. Cleared by the "clear" link.
 */
export default function ChatBar({ onAction }) {
  const [history, setHistory] = useState(loadHistory)
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [collapsed, setCollapsed] = useState(false)
  const messagesEndRef = useRef(null)

  // Persist history whenever it changes
  useEffect(() => {
    saveHistory(history)
  }, [history])

  // Scroll to newest message on update
  useEffect(() => {
    if (messagesEndRef.current && !collapsed) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' })
    }
  }, [history, collapsed])

  async function handleSubmit(event) {
    event.preventDefault()
    const trimmed = input.trim()
    if (!trimmed || busy) return

    // Optimistically append the user's message
    const userTurn = { role: 'user', content: trimmed }
    const nextHistory = [...history, userTurn].slice(-MAX_HISTORY_TURNS)
    setHistory(nextHistory)
    setInput('')
    setBusy(true)

    try {
      const result = await sendChat(trimmed, nextHistory.slice(-HISTORY_FOR_PROMPT - 1, -1))
      const assistantTurn = { role: 'assistant', content: result.reply }
      setHistory((prev) => [...prev, assistantTurn].slice(-MAX_HISTORY_TURNS))

      if (result.intent === 'add_commitment' && result.commitment) {
        toast.success(`Added: ${result.commitment.text}`)
        if (onAction) onAction()
      }
    } catch (err) {
      const msg = err.message?.includes('503')
        ? "I'm having trouble thinking right now. Try again in a moment."
        : err.message || 'Something went wrong.'
      setHistory((prev) =>
        [...prev, { role: 'assistant', content: msg, error: true }].slice(-MAX_HISTORY_TURNS),
      )
    } finally {
      setBusy(false)
    }
  }

  function handleClear() {
    setHistory([])
    saveHistory([])
  }

  return (
    <div className="fixed inset-x-0 bottom-0 z-40 pointer-events-none">
      {/* Gradient fade above the bar so content underneath isn't abruptly cut */}
      <div className="h-12 bg-gradient-to-t from-[#0f0f0f] to-transparent" />

      <div className="bg-[#0f0f0f] border-t border-white/[0.06] pointer-events-auto">
        <div className="max-w-2xl mx-auto px-6 py-3">
          {/* Message history — collapsed by default if empty */}
          {history.length > 0 && !collapsed && (
            <div className="max-h-48 overflow-y-auto mb-3 space-y-2 pr-1">
              {history.slice(-6).map((turn, i) => (
                <ChatMessage key={`${history.length}-${i}`} turn={turn} />
              ))}
              <div ref={messagesEndRef} />
            </div>
          )}

          {/* Input row */}
          <form onSubmit={handleSubmit} className="flex items-center gap-2">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Talk to Overwatch…"
              disabled={busy}
              className="flex-1 px-4 py-3 bg-[#1a1a1a] border border-[#2a2a2a] rounded-lg text-[#f5f5f5] text-sm placeholder:text-zinc-600 focus:outline-none focus:border-orange-500 transition-colors"
            />
            <button
              type="submit"
              disabled={busy || !input.trim()}
              className="px-5 py-3 bg-orange-500 hover:bg-orange-600 disabled:bg-[#2a2a2a] disabled:text-zinc-600 disabled:cursor-not-allowed text-black font-semibold rounded-lg text-sm transition-colors"
            >
              {busy ? '…' : 'Send'}
            </button>
          </form>

          {/* Bottom toolbar — only relevant if there's history */}
          {history.length > 0 && (
            <div className="flex items-center gap-3 mt-2 text-[10px] text-zinc-600">
              <button
                onClick={() => setCollapsed((c) => !c)}
                className="hover:text-orange-500 transition-colors uppercase tracking-widest"
              >
                {collapsed ? 'show history' : 'hide history'}
              </button>
              <span className="text-zinc-800">·</span>
              <button
                onClick={handleClear}
                className="hover:text-red-500 transition-colors uppercase tracking-widest"
              >
                clear
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function ChatMessage({ turn }) {
  const isUser = turn.role === 'user'
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[80%] px-3 py-2 rounded-lg text-sm leading-snug ${
          isUser
            ? 'bg-orange-500/[0.12] border border-orange-500/30 text-orange-100'
            : turn.error
              ? 'bg-red-900/20 border border-red-900/40 text-red-300'
              : 'bg-[#1a1a1a] border border-[#2a2a2a] text-zinc-200'
        }`}
      >
        {turn.content}
      </div>
    </div>
  )
}
