import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { sendChat } from '../api'
import { useSpeechRecognition } from '../hooks/useSpeechRecognition'
import { speak, cancelSpeech, isSpeechSynthesisSupported } from '../lib/speech'

const HISTORY_KEY = 'overwatch.chat.history'
const SPEAK_KEY = 'overwatch.chat.speakReplies'
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
export default function ChatBar({ onAction, onHeightChange }) {
  const [history, setHistory] = useState(loadHistory)
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [collapsed, setCollapsed] = useState(false)
  // When on, the assistant's replies are spoken aloud (text-to-speech).
  // Off by default so audio never starts unexpectedly. Persisted.
  const [speakReplies, setSpeakReplies] = useState(
    () => localStorage.getItem(SPEAK_KEY) === '1',
  )
  const messagesEndRef = useRef(null)
  // Measured by ResizeObserver so the parent can reserve enough
  // padding-bottom to never hide content behind us — especially when
  // the history panel expands on a phone.
  const containerRef = useRef(null)

  // Speech-to-text. Transcript (interim + final) streams into the input so
  // the user sees words appear as they speak and can review/edit before
  // sending — safer than auto-sending a misheard command.
  const {
    supported: micSupported,
    listening,
    error: micError,
    start: startListening,
    stop: stopListening,
  } = useSpeechRecognition({ onResult: (text) => setInput(text) })

  // Surface mic errors (most commonly a denied permission) as a toast.
  useEffect(() => {
    if (!micError) return
    if (micError === 'not-allowed' || micError === 'service-not-allowed') {
      toast.error('Microphone access denied. Enable it in your browser settings.')
    } else if (micError === 'no-speech') {
      toast.message("Didn't catch that — try again.")
    }
  }, [micError])

  // Persist the speak-replies toggle.
  useEffect(() => {
    localStorage.setItem(SPEAK_KEY, speakReplies ? '1' : '0')
    if (!speakReplies) cancelSpeech()
  }, [speakReplies])

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

  // Watch our container's real height and notify the parent.
  // ResizeObserver fires on history expand/collapse, input growth, viewport
  // change, font load — covers every case where we'd otherwise overlap.
  useEffect(() => {
    if (!containerRef.current || !onHeightChange) return
    const el = containerRef.current
    const observer = new ResizeObserver(([entry]) => {
      onHeightChange(entry.contentRect.height)
    })
    observer.observe(el)
    // Report initial height immediately so the first paint already has
    // the right padding even before any user interaction.
    onHeightChange(el.getBoundingClientRect().height)
    return () => observer.disconnect()
  }, [onHeightChange])

  function toggleListening() {
    if (listening) {
      stopListening()
    } else {
      cancelSpeech() // don't talk over the user
      startListening()
    }
  }

  async function handleSubmit(event) {
    event.preventDefault()
    if (listening) stopListening()
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

      // Speak the reply aloud if the user enabled text-to-speech.
      if (speakReplies && result.reply) speak(result.reply)

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

      <div ref={containerRef} className="bg-[#0f0f0f] border-t border-white/[0.06] pointer-events-auto">
        <div className="w-full md:w-[70vw] max-w-[1280px] mx-auto px-6 py-3">
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
            {/* Mic button — only when the browser can transcribe. Pulses
                orange while listening. */}
            {micSupported && (
              <button
                type="button"
                onClick={toggleListening}
                disabled={busy}
                aria-label={listening ? 'Stop listening' : 'Speak to Overwatch'}
                title={listening ? 'Stop listening' : 'Speak to Overwatch'}
                className={`shrink-0 p-3 rounded-lg border transition-colors ${
                  listening
                    ? 'bg-orange-500/20 border-orange-500 text-orange-400 animate-pulse'
                    : 'bg-[#1a1a1a] border-[#2a2a2a] text-zinc-400 hover:text-orange-400 hover:border-orange-500/50'
                }`}
              >
                <MicIcon />
              </button>
            )}
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={listening ? 'Listening…' : 'Talk to Overwatch…'}
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

          {/* Bottom toolbar — shows when there's history, or whenever
              text-to-speech is available (for the speak toggle). */}
          {(history.length > 0 || isSpeechSynthesisSupported()) && (
            <div className="flex items-center gap-3 mt-2 text-[10px] text-zinc-600">
              {isSpeechSynthesisSupported() && (
                <button
                  onClick={() => setSpeakReplies((s) => !s)}
                  className={`uppercase tracking-widest transition-colors ${
                    speakReplies ? 'text-orange-500' : 'hover:text-orange-500'
                  }`}
                  title="Speak Overwatch's replies aloud"
                >
                  {speakReplies ? '🔊 speak: on' : 'speak: off'}
                </button>
              )}
              {history.length > 0 && (
                <>
                  <span className="text-zinc-800">·</span>
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
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

/** Microphone glyph (inline SVG, no dependency). */
function MicIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
      <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
      <line x1="12" y1="19" x2="12" y2="23" />
      <line x1="8" y1="23" x2="16" y2="23" />
    </svg>
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
