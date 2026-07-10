import { useCallback, useRef, useState } from 'react'
import { speak, cancelSpeech, isSpeechSynthesisSupported } from '../lib/speech'
import { speakNative, cancelNativeSpeech, isNativeTtsSupported } from '../lib/nativeTts'

/**
 * useSpeechSynthesis — React wrapper over text-to-speech.
 *
 * Mirrors useSpeechRecognition's native/web dispatch: on the native
 * (Capacitor) app the WebView's speechSynthesis is unreliable, so we use the
 * device's real TTS engine via @capacitor-community/text-to-speech; on the
 * web we use the browser's Web Speech API (lib/speech.js).
 *
 * Returns:
 *   supported  boolean            Whether this platform can speak at all.
 *   speaking   boolean            True while an utterance is in progress.
 *   speak(text)                   Speak text aloud (flushes any in-progress speech).
 *   cancel()                      Stop any in-progress speech immediately.
 */
export function useSpeechSynthesis() {
  // Native app → the device's TTS engine. Web → the browser's Web Speech API.
  const native = isNativeTtsSupported()
  const supported = native || isSpeechSynthesisSupported()
  const [speaking, setSpeaking] = useState(false)
  // Guards a stale onEnd (from a since-cancelled/replaced utterance) from
  // clobbering the speaking state of a newer one.
  const tokenRef = useRef(0)

  const speakText = useCallback(
    (text) => {
      if (!supported || !text) return
      const token = ++tokenRef.current
      setSpeaking(true)
      const onEnd = () => {
        if (tokenRef.current === token) setSpeaking(false)
      }
      if (native) {
        speakNative(text, { onEnd })
      } else {
        speak(text, { onEnd })
      }
    },
    [supported, native],
  )

  const cancel = useCallback(() => {
    tokenRef.current++ // invalidate any pending onEnd from the cancelled utterance
    setSpeaking(false)
    if (native) {
      cancelNativeSpeech()
    } else {
      cancelSpeech()
    }
  }, [native])

  return { supported, speaking, speak: speakText, cancel }
}
