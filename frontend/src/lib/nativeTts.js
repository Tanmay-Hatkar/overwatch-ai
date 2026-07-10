/**
 * nativeTts.js — Text-to-speech on the native (Capacitor) app.
 *
 * The Android WebView's built-in `speechSynthesis` is unreliable (null on
 * some OEM WebViews, e.g. Huawei, and `SpeechSynthesisVoice` type errors on
 * others — see capacitor-community/text-to-speech issues #62 and #7), so on
 * native we use the @capacitor-community/text-to-speech plugin (the
 * device's real TTS engine). This module exposes the SAME shape as
 * lib/speech.js's speak()/cancelSpeech()/isSpeechSynthesisSupported() so the
 * hook can swap implementations transparently.
 *
 * Important: the plugin's speak() promise resolves when the utterance
 * actually finishes (Android's onDone callback) and rejects on error or on
 * an interrupting stop() — unlike the Web Speech API's callback-based
 * SpeechSynthesisUtterance. We bridge both outcomes to the same onEnd
 * callback shape lib/speech.js uses, so callers don't need to care which
 * implementation is active.
 */

import { TextToSpeech } from '@capacitor-community/text-to-speech'
import { isNative } from './native'

/** True if native text-to-speech is usable (native app + plugin present). */
export function isNativeTtsSupported() {
  return isNative()
}

/**
 * Speak text aloud via the native TTS engine. No-op if text is empty.
 *
 * @param {string} text  What to say.
 * @param {object} [opts]
 * @param {() => void} [opts.onEnd]  Fired when speech finishes, fails, or is
 *   cancelled — always fired exactly once, mirroring lib/speech.js's speak().
 */
export async function speakNative(text, { onEnd } = {}) {
  if (!text) {
    onEnd?.()
    return
  }
  try {
    // The plugin flushes any in-flight utterance by default (QueueStrategy
    // .Flush), so replies never queue up — same behavior as
    // window.speechSynthesis.cancel() before speak() in lib/speech.js.
    await TextToSpeech.speak({
      text,
      lang: navigator.language || 'en-US',
      rate: 1.0,
      pitch: 1.0,
      volume: 1.0,
    })
  } catch {
    // Rejects on synth error or when cancelNativeSpeech() interrupts it —
    // either way, the utterance is over.
  } finally {
    onEnd?.()
  }
}

/** Stop any in-progress native speech immediately. */
export async function cancelNativeSpeech() {
  try {
    await TextToSpeech.stop()
  } catch {
    // ignore — nothing was speaking
  }
}
