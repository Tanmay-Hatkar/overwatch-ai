# 0016: Native text-to-speech on the Android app

- **Status:** Accepted
- **Date:** 2026-07-09
- **Deciders:** Tanmay Hatkar

## Context

ADR-0012 shipped voice input/output via the browser-native Web Speech API:
`SpeechRecognition` for speech-to-text (STT) and `window.speechSynthesis`
for text-to-speech (TTS), wrapped in `lib/speech.js`. That ADR flagged the
Capacitor Android app's WebView speech support as unreliable and scoped a
native fix to "later." STT got that fix first — `lib/nativeSpeech.js` +
`hooks/useSpeechRecognition.js` dispatch to
`@capacitor-community/speech-recognition` when running in the native app,
falling back to the Web Speech API on the web. TTS did not get the
equivalent treatment, so the "speak: on" toggle in `ChatBar.jsx` still ran
through the WebView's `speechSynthesis` on Android — the same class of
unreliable surface STT already moved off of.

Concretely, Android WebView's `speechSynthesis` is known to be
inconsistent across OEM builds:
- `window.speechSynthesis` is `null`/`undefined` on some WebViews (e.g.
  Huawei), so `isSpeechSynthesisSupported()` fails outright —
  `capacitor-community/text-to-speech` issue #62.
- `SpeechSynthesisVoice`-related type errors surface on other WebViews when
  enumerating or selecting voices — issue #7.

Net effect: the "speak replies aloud" toggle silently does nothing (or
errors) for a meaningful slice of native Android users, right after STT was
made reliable for the same audience. That's an inconsistent voice
experience within the same app.

Constraints (same as ADR-0012):
- No backend changes — TTS is a pure client capability.
- The web/desktop path (Vercel-deployed PWA, Chrome reviewers) must keep
  working exactly as-is; this is additive for the native app only.
- Match the existing native-STT pattern exactly — same file layout, same
  dispatch philosophy — so the codebase has one consistent way of doing
  "native when in the Capacitor app, web fallback otherwise."

## Decision

**Add `@capacitor-community/text-to-speech` (MIT) as the native TTS engine
for the Android app, dispatched behind the same native/web seam STT already
uses. The Web Speech API in `lib/speech.js` remains the permanent web/
desktop implementation (per ADR-0012) — this is purely additive for native.**

### Architecture (mirrors ADR-0012's STT pattern)
- `lib/nativeTts.js` — native implementation. Exposes
  `isNativeTtsSupported()`, `speakNative(text, {onEnd})`, and
  `cancelNativeSpeech()` — the same shape as `lib/speech.js`'s
  `speak()`/`cancelSpeech()`/`isSpeechSynthesisSupported()`, so the hook can
  swap implementations transparently. `speakNative()` bridges the plugin's
  promise-based `speak()` (which resolves on Android's `onDone` callback, or
  rejects on error/interruption) to the same `onEnd` callback shape
  `lib/speech.js` uses, so callers never need to know which engine is
  active.
- `hooks/useSpeechSynthesis.js` — new hook, mirrors
  `useSpeechRecognition.js`'s dispatch: `isNativeTtsSupported()` (native app
  → `@capacitor-community/text-to-speech`) vs. `isSpeechSynthesisSupported()`
  (web → `window.speechSynthesis`). Exposes
  `{supported, speaking, speak(text), cancel()}`.
- `ChatBar.jsx` — swapped its direct `lib/speech.js` imports
  (`speak`/`cancelSpeech`/`isSpeechSynthesisSupported`) for
  `useSpeechSynthesis()`. No behavior change: the "speak: on/off" toggle,
  its localStorage persistence, and "starting to listen cancels
  in-progress speech" are all preserved — they just call through the hook
  now instead of the module directly.

### Why this plugin
- MIT-licensed, same publisher family (`@capacitor-community`) and
  version-compatibility profile as `@capacitor-community/speech-recognition`,
  which is already vetted and shipped for STT.
- Uses the device's real TTS engine (Android `TextToSpeech` API) instead of
  the WebView's — the same fix STT already applied.
- Its `speak()` promise resolves on the engine's `onDone` callback (verified
  in the plugin's Android source, `TextToSpeech.java`), giving us a real
  "finished speaking" signal — better than the Web Speech API's
  `utterance.onend`, which is exactly what we already rely on in
  `lib/speech.js`.

## Alternatives considered

### Self-hosted / server-side TTS (Piper, or a cloud TTS API)
Run TTS server-side and stream synthesized audio to the client.

**Rejected because:**
- Reintroduces backend surface (an endpoint, audio streaming/buffering,
  request latency) for a capability the client can already do locally and
  for free.
- Overwatch's infra budget is ~$1-5/month on Railway — hosting a TTS model
  (Piper) or paying per-character for a cloud TTS API doesn't fit that, and
  buys nothing STT's equivalent decision (ADR-0012) didn't already reject
  for the same reason.
- A native device TTS engine has no marginal cost, no network dependency,
  and no latency — strictly better fit for this app's constraints.

### Leave TTS on the Web Speech API everywhere, including native
Do nothing; accept the WebView's unreliable `speechSynthesis` on Android.

**Rejected because:**
- Directly reintroduces the reliability gap STT already closed, for the
  same user population, with documented failure modes (issues #62, #7)
  rather than a hypothetical one.
- Leaves the "speak: on" toggle silently broken on some Android OEM
  WebViews — a worse experience than just hiding the control, since the
  toggle appears to work (feature-detection may pass) but nothing is heard.

### A different native TTS plugin, or writing a custom Capacitor plugin
**Rejected because:**
- `@capacitor-community/text-to-speech` already covers what's needed
  (text, lang, rate, pitch, volume, stop) with an actively maintained
  Android/iOS implementation — no reason to hand-roll a plugin STT's
  ecosystem sibling already solved.

## Consequences

### Positive
- **Consistent native voice experience.** STT and TTS are now both native
  on Android, closing the one-sided gap ADR-0012 left open.
- **Zero backend change, zero new infra, zero recurring cost** — same
  posture as ADR-0012's STT decision.
- **Clean extension seam preserved.** `useSpeechSynthesis.js` is now the
  single place UI code asks "can I speak, and how" — a future cloud TTS
  provider (if ever wanted) plugs in behind the same hook without touching
  `ChatBar.jsx`.
- **No UI/UX change.** The toggle, persistence, and "listening cancels
  speaking" behavior are unchanged — this is purely an implementation swap
  underneath.

### Negative
- **Android-only fix.** iOS Capacitor builds (not currently shipped) would
  still route through the web fallback unless/until iOS is built and
  tested against this same plugin.
- **One more native dependency to keep in sync** with Capacitor core
  version bumps, mirroring the STT plugin's maintenance burden.
- **Voice quality is still "whatever the device's TTS engine provides,"**
  same tradeoff STT already accepted for recognition quality — acceptable,
  consistent with ADR-0012.

### Future considerations
- iOS native TTS support, if/when an iOS build is added — same plugin
  supports it.
- Exposing rate/pitch/voice selection as a user setting (the plugin
  supports all three; `lib/speech.js` and `lib/nativeTts.js` currently hardcode
  defaults, same as ADR-0012's original STT/TTS scope).
- Revisit cloud TTS (e.g. for a more natural/branded voice) only if product
  need clearly outweighs the added backend surface and cost this ADR just
  rejected.

## References
- ADR-0012 — the Web Speech API decision this extends; native STT precedent
- `frontend/src/lib/nativeSpeech.js` — the STT pattern this mirrors
- `frontend/src/lib/nativeTts.js` — the native TTS wrapper
- `frontend/src/hooks/useSpeechSynthesis.js` — the dispatch hook
- `frontend/src/components/ChatBar.jsx` — the speak toggle, now hook-driven
- [capacitor-community/text-to-speech](https://github.com/capacitor-community/text-to-speech)
- [capacitor-community/text-to-speech issue #62](https://github.com/capacitor-community/text-to-speech/issues/62) — null `speechSynthesis` on some WebViews (e.g. Huawei)
- [capacitor-community/text-to-speech issue #7](https://github.com/capacitor-community/text-to-speech/issues/7) — `SpeechSynthesisVoice` type errors
