/**
 * nativeSpeech.js — Speech-to-text on the native (Capacitor) app.
 *
 * The Android WebView's built-in webkitSpeechRecognition doesn't work, so on
 * native we use the @capacitor-community/speech-recognition plugin (the
 * device's real speech engine). This module exposes the SAME shape as
 * lib/speech.js's createRecognizer() — start/stop/abort + onResult/onError/
 * onEnd — so the hook can swap implementations transparently.
 *
 * Important: with partialResults=true the plugin's start() promise resolves
 * IMMEDIATELY (right after listening begins), NOT when speech ends. So we
 * detect the real end via the 'listeningState' event — otherwise the mic
 * would shut off a fraction of a second after starting.
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
  let stateListener = null
  let running = false
  let lastText = ''

  async function removeListeners() {
    for (const l of [partialListener, stateListener]) {
      if (l) {
        try {
          await l.remove()
        } catch {
          // ignore
        }
      }
    }
    partialListener = null
    stateListener = null
  }

  async function finish() {
    if (!running) return
    running = false
    // Emit whatever we last heard as the final transcript.
    if (lastText) onResult?.(lastText, true)
    await removeListeners()
    onEnd?.()
  }

  return {
    start: async () => {
      if (running) return
      lastText = ''
      try {
        // Make sure a recognizer exists on this device.
        try {
          const avail = await SpeechRecognition.available()
          if (avail && avail.available === false) {
            onError?.('not-supported')
            return
          }
        } catch {
          // older plugin versions may not implement available(); proceed
        }

        const perm = await SpeechRecognition.requestPermissions()
        if (perm.speechRecognition !== 'granted') {
          onError?.('not-allowed')
          return
        }

        running = true

        partialListener = await SpeechRecognition.addListener(
          'partialResults',
          (data) => {
            const text = (data && data.matches && data.matches[0]) || ''
            if (text) {
              lastText = text
              onResult?.(text, false)
            }
          },
        )

        // The real "it stopped listening" signal — drives onEnd, so the
        // mic button stays active while the user is actually speaking.
        stateListener = await SpeechRecognition.addListener(
          'listeningState',
          (data) => {
            if (data && data.status === 'stopped') {
              finish()
            }
          },
        )

        // Resolves immediately with partialResults=true — do NOT finish here.
        await SpeechRecognition.start({
          language: 'en-US',
          maxResults: 1,
          partialResults: true,
          popup: false,
        })
      } catch (e) {
        onError?.(e?.message || 'unknown')
        running = false
        await removeListeners()
        onEnd?.()
      }
    },
    stop: async () => {
      try {
        await SpeechRecognition.stop()
      } catch {
        // ignore
      }
      await finish()
    },
    abort: async () => {
      running = false
      try {
        await SpeechRecognition.stop()
      } catch {
        // ignore
      }
      await removeListeners()
      onEnd?.()
    },
  }
}
