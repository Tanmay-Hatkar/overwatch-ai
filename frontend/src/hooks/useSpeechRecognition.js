import { useCallback, useEffect, useRef, useState } from 'react'
import { createRecognizer, isSpeechRecognitionSupported } from '../lib/speech'

/**
 * useSpeechRecognition — React wrapper over the speech recognizer.
 *
 * Returns:
 *   supported    boolean   Whether the browser can transcribe at all.
 *   listening    boolean   True while actively listening.
 *   transcript   string    The latest (interim or final) transcript.
 *   error        string|null  Last recognition error code, if any.
 *   start()      Begin listening (clears prior transcript/error).
 *   stop()       Stop listening.
 *
 * @param {object} [opts]
 * @param {(text: string, isFinal: boolean) => void} [opts.onResult]  Called on
 *   every transcript update (interim and final). The place to mirror the text
 *   into an input field — fired from a recognition event, not a render effect.
 */
export function useSpeechRecognition({ onResult } = {}) {
  const supported = isSpeechRecognitionSupported()
  const [listening, setListening] = useState(false)
  const [transcript, setTranscript] = useState('')
  const [error, setError] = useState(null)
  const recognizerRef = useRef(null)
  // Keep the latest onResult without re-creating the recognizer each render.
  const onResultRef = useRef(onResult)
  useEffect(() => {
    onResultRef.current = onResult
  }, [onResult])

  // Build the recognizer once. Its callbacks drive our state.
  useEffect(() => {
    if (!supported) return
    recognizerRef.current = createRecognizer({
      onResult: (text, isFinal) => {
        setTranscript(text)
        onResultRef.current?.(text, isFinal)
      },
      onError: (code) => {
        setError(code)
        setListening(false)
      },
      onEnd: () => setListening(false),
    })
    return () => recognizerRef.current?.abort()
  }, [supported])

  const start = useCallback(() => {
    if (!recognizerRef.current || listening) return
    setTranscript('')
    setError(null)
    setListening(true)
    recognizerRef.current.start()
  }, [listening])

  const stop = useCallback(() => {
    recognizerRef.current?.stop()
    setListening(false)
  }, [])

  return { supported, listening, transcript, error, start, stop }
}
