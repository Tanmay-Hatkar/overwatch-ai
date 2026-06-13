/**
 * nativeSpeech.js — Speech-to-text on the native (Capacitor) app.
 *
 * The Android WebView's built-in webkitSpeechRecognition doesn't work, so on
 * native we use the @capacitor-community/speech-recognition plugin (the
 * device's real speech engine). This module exposes the SAME shape as
 * lib/speech.js's createRecognizer() — start/stop/abort + onResult/onError/
 * onEnd — so the hook can swap implementations transparently.
 */

import { SpeechRecognition } from '@capacitor-community/speech-recognition'
import { isNative } from './native'

/** True if native speech-to-text is usable (native app + plugin present). */
export function isNativeSpeechSupported() {
  return isNative()
}

/**
 * Create a native recognizer mirroring createRecognizer()'s interface.
 *
 * @param {object} cb
 * @param {(text: string, isFinal: boolean) => void} cb.onResult
 * @param {(code: string) => void} [cb.onError]
 * @param {() => void} [cb.onEnd]
 */
export function createNativeRecognizer({ onResult, onError, onEnd }) {
  let partialListener = null
  let running = false

  async function cleanup() {
    running = false
    if (partialListener) {
      try {
        await partialListener.remove()
      } catch {
        // ignore
      }
      partialListener = null
    }
    onEnd?.()
  }

  return {
    start: async () => {
      if (running) return
      try {
        const perm = await SpeechRecognition.requestPermissions()
        if (perm.speechRecognition !== 'granted') {
          onError?.('not-allowed')
          return
        }
        running = true
        // Stream partial results into onResult as the user speaks.
        partialListener = await SpeechRecognition.addListener(
          'partialResults',
          (data) => {
            const text = (data?.matches && data.matches[0]) || ''
            if (text) onResult?.(text, false)
          },
        )
        // start() resolves with final matches when recognition completes.
        const result = await SpeechRecognition.start({
          language: 'en-US',
          maxResults: 1,
          partialResults: true,
          popup: false,
        })
        const finalText = (result?.matches && result.matches[0]) || ''
        if (finalText) onResult?.(finalText, true)
        await cleanup()
      } catch (e) {
        onError?.(e?.message || 'unknown')
        await cleanup()
      }
    },
    stop: async () => {
      try {
        await SpeechRecognition.stop()
      } catch {
        // ignore
      }
      await cleanup()
    },
    abort: async () => {
      try {
        await SpeechRecognition.stop()
      } catch {
        // ignore
      }
      await cleanup()
    },
  }
}
