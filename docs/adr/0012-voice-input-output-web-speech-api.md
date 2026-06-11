# 0012: Voice input/output via the Web Speech API

- **Status:** Accepted
- **Date:** 2026-06-11
- **Deciders:** Tanmay Hatkar

## Context

Voice has been the headline future-feature since the start — "talk to
Overwatch, no typing." The chat surface (ADR-0008) made the product
conversational in text; voice is the natural completion of that mechanic,
and it's the single most demoable upgrade for an upcoming review.

Two halves:
- **Speech-to-text (STT):** speak a commitment or question → it becomes a
  chat message.
- **Text-to-speech (TTS):** Overwatch speaks its reply → eyes-free use.

Constraints:
- We're shipping the *web* surface first (deployed on Vercel, opened in
  Chrome by reviewers) — fast, zero new infra, demoable this week.
- A Capacitor Android app exists; its WebView's speech support is
  unreliable, so the native app will later swap STT for a native plugin.
- No backend changes wanted — voice is purely a client capability feeding
  the existing `/chat` endpoint.

## Decision

**Use the browser-native Web Speech API — `SpeechRecognition` for STT and
`speechSynthesis` for TTS — wrapped in a feature-detected client module,
with the mic feeding the existing chat input and TTS as an opt-in toggle.**

### Architecture
- `lib/speech.js` — thin wrapper: `createRecognizer()`,
  `speak()`/`cancelSpeech()`, and `isSpeechRecognitionSupported()` /
  `isSpeechSynthesisSupported()` feature detectors.
- `hooks/useSpeechRecognition.js` — React hook exposing
  `{supported, listening, transcript, error, start, stop}`.
- `ChatBar.jsx` — a mic button (shown only when STT is supported) and a
  "speak: on/off" toggle (shown only when TTS is supported).

### UX decisions
- **STT fills the input; it does NOT auto-send.** The final transcript lands
  in the text field so the user reviews/edits before sending — a misheard
  "delete everything" should never auto-execute. Interim results stream
  into the input live so the user sees words as they speak.
- **TTS is opt-in and off by default**, persisted in localStorage. Audio
  never starts unexpectedly. Starting to listen cancels any in-progress
  speech so the app doesn't talk over the user.
- **Graceful absence:** unsupported capabilities hide their controls rather
  than showing broken buttons. Denied mic permission surfaces a toast.

## Alternatives considered

### Cloud STT/TTS (OpenAI Whisper, Google Speech, ElevenLabs)
Send audio to a hosted transcription/synthesis service.

**Rejected (for now) because:**
- Adds backend endpoints, audio upload, latency, and per-use cost
- Requires streaming/recording plumbing we don't have
- The Web Speech API is free, on-device, and zero-infra — right for v1
- We can add a cloud provider later behind the same `lib/speech.js`
  interface if quality demands it

### Native speech plugin first (Capacitor community plugins)
Build STT/TTS natively in the Android app from the start.

**Rejected as the first step because:**
- The reviewer will use the deployed *web* app — web voice is what's
  demoable this week
- The native plugin is additive: `lib/speech.js` becomes the web
  implementation; the native app swaps in a plugin behind the same hook
  later, no UI changes

### Auto-send on final transcript
Speak → transcribe → immediately POST to `/chat`.

**Rejected because:**
- Speech recognition errors would silently create wrong commitments or
  fire unintended actions
- "Review before send" is the safer default for a tool that mutates state;
  we can add a power-user auto-send setting later

## Consequences

### Positive
- **The product is genuinely voice-enabled** — talk to add commitments and
  ask questions; optionally hear replies. The headline feature is real.
- **Zero backend change, zero new infra, zero cost.** Pure client feature
  over the existing chat endpoint.
- **Demoable immediately** on the deployed web app in Chrome.
- **Clean extension seam:** `lib/speech.js` is the swap point for native
  plugins or cloud providers later.

### Negative
- **Browser-dependent.** Excellent in Chrome (desktop + Android); STT is
  flaky in Safari/iOS and often absent in Firefox. We feature-detect and
  hide controls, so it degrades to text gracefully — but iOS PWA users
  won't get reliable STT until the native plugin lands.
- **No custom wake word / continuous mode.** It's tap-to-talk, one
  utterance at a time (`continuous = false`) — deliberate, to avoid a
  hot mic and runaway transcription.
- **TTS voice is the system voice** — quality varies by OS. Acceptable;
  a cloud TTS swap is possible later.

### Future considerations
- Native Capacitor STT/TTS plugins for the Android app (reliable iOS-class
  speech), behind the same hook.
- Optional cloud STT (Whisper) for higher accuracy, behind `lib/speech.js`.
- A power-user "auto-send after speaking" setting.
- Continuous/hands-free mode with silence-based finalization (mirrors what
  v1 explored).

## References
- ADR-0008 — the conversational chat surface this completes
- `frontend/src/lib/speech.js` — the Web Speech API wrapper
- `frontend/src/hooks/useSpeechRecognition.js` — the React hook
- `frontend/src/components/ChatBar.jsx` — mic button + speak toggle
- [MDN: Web Speech API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API)
