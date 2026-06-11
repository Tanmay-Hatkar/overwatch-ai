/**
 * speech.js — Thin wrapper over the browser Web Speech API.
 *
 * Two capabilities, each independently feature-detected so the UI can hide
 * controls the browser doesn't support (rather than showing broken buttons):
 *
 *   - Speech-to-text (SpeechRecognition)  → talk to Overwatch
 *   - Text-to-speech (speechSynthesis)    → Overwatch speaks replies
 *
 * Support reality (why we feature-detect):
 *   - Chrome desktop / Chrome Android: both work well
 *   - Safari/iOS: recognition is flaky; synthesis works
 *   - Firefox: recognition often unavailable
 * On the native Capacitor app we'll later swap recognition for a native
 * plugin (the WebView's SpeechRecognition is unreliable); this module stays
 * the web implementation.
 */

// SpeechRecognition is still vendor-prefixed in most browsers.
const SpeechRecognition =
  typeof window !== 'undefined'
    ? window.SpeechRecognition || window.webkitSpeechRecognition
    : undefined

/** True if the browser can transcribe speech. */
export function isSpeechRecognitionSupported() {
  return Boolean(SpeechRecognition)
}

/** True if the browser can speak text aloud. */
export function isSpeechSynthesisSupported() {
  return typeof window !== 'undefined' && 'speechSynthesis' in window
}

/**
 * Create a speech recognizer.
 *
 * Returns an object with start()/stop()/abort(). Results stream back through
 * the callbacks: interim transcripts as the user speaks, then a final
 * transcript when a phrase completes.
 *
 * @param {object} cb
 * @param {(text: string, isFinal: boolean) => void} cb.onResult  Transcript updates.
 * @param {(code: string) => void} [cb.onError]  Error code (e.g. 'no-speech', 'not-allowed').
 * @param {() => void} [cb.onEnd]  Fired when recognition stops (silence, stop(), or error).
 * @returns {{start: () => void, stop: () => void, abort: () => void} | null}
 *   Null if recognition isn't supported.
 */
export function createRecognizer({ onResult, onError, onEnd }) {
  if (!SpeechRecognition) return null

  const recognition = new SpeechRecognition()
  recognition.continuous = false      // stop after one utterance (a command)
  recognition.interimResults = true   // stream partial text for live feedback
  recognition.lang = navigator.language || 'en-US'
  recognition.maxAlternatives = 1

  recognition.onresult = (event) => {
    // Concatenate everything from this session; mark final when the last
    // result is final. interimResults means we get progressive updates.
    let transcript = ''
    let isFinal = false
    for (let i = event.resultIndex; i < event.results.length; i++) {
      transcript += event.results[i][0].transcript
      if (event.results[i].isFinal) isFinal = true
    }
    onResult?.(transcript.trim(), isFinal)
  }

  recognition.onerror = (event) => {
    onError?.(event.error || 'unknown')
  }

  recognition.onend = () => {
    onEnd?.()
  }

  return {
    start: () => {
      try {
        recognition.start()
      } catch {
        // start() throws if called while already running — safe to ignore.
      }
    },
    stop: () => {
      try {
        recognition.stop()
      } catch {
        // ignore
      }
    },
    abort: () => {
      try {
        recognition.abort()
      } catch {
        // ignore
      }
    },
  }
}

/**
 * Speak text aloud. No-op if synthesis is unsupported.
 *
 * @param {string} text  What to say.
 * @param {object} [opts]
 * @param {() => void} [opts.onEnd]  Fired when speech finishes.
 */
export function speak(text, { onEnd } = {}) {
  if (!isSpeechSynthesisSupported() || !text) {
    onEnd?.()
    return
  }
  // Cancel anything already speaking so replies don't queue up.
  window.speechSynthesis.cancel()
  const utterance = new SpeechSynthesisUtterance(text)
  utterance.lang = navigator.language || 'en-US'
  utterance.rate = 1.0
  utterance.pitch = 1.0
  if (onEnd) utterance.onend = onEnd
  window.speechSynthesis.speak(utterance)
}

/** Stop any in-progress speech immediately. */
export function cancelSpeech() {
  if (isSpeechSynthesisSupported()) window.speechSynthesis.cancel()
}
