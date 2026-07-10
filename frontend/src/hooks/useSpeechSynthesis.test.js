import { describe, it, expect, vi, beforeEach } from 'vitest'
import { act, renderHook } from '@testing-library/react'

// Mock both implementations before importing the hook so it picks up the
// mocked module bindings.
vi.mock('../lib/speech', () => ({
  speak: vi.fn(),
  cancelSpeech: vi.fn(),
  isSpeechSynthesisSupported: vi.fn(),
}))
vi.mock('../lib/nativeTts', () => ({
  speakNative: vi.fn(),
  cancelNativeSpeech: vi.fn(),
  isNativeTtsSupported: vi.fn(),
}))

import { speak, cancelSpeech, isSpeechSynthesisSupported } from '../lib/speech'
import { speakNative, cancelNativeSpeech, isNativeTtsSupported } from '../lib/nativeTts'
import { useSpeechSynthesis } from './useSpeechSynthesis'

describe('useSpeechSynthesis', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('on the native (Capacitor) app', () => {
    beforeEach(() => {
      isNativeTtsSupported.mockReturnValue(true)
      isSpeechSynthesisSupported.mockReturnValue(false) // shouldn't matter — native wins
    })

    it('reports supported and dispatches speak() to the native plugin', () => {
      const { result } = renderHook(() => useSpeechSynthesis())
      expect(result.current.supported).toBe(true)

      act(() => result.current.speak('hello there'))

      expect(speakNative).toHaveBeenCalledTimes(1)
      expect(speakNative).toHaveBeenCalledWith('hello there', { onEnd: expect.any(Function) })
      expect(speak).not.toHaveBeenCalled()
      expect(result.current.speaking).toBe(true)
    })

    it('dispatches cancel() to the native plugin', () => {
      const { result } = renderHook(() => useSpeechSynthesis())
      act(() => result.current.speak('hello'))
      act(() => result.current.cancel())

      expect(cancelNativeSpeech).toHaveBeenCalledTimes(1)
      expect(cancelSpeech).not.toHaveBeenCalled()
      expect(result.current.speaking).toBe(false)
    })

    it('flips speaking back to false when the native onEnd callback fires', () => {
      const { result } = renderHook(() => useSpeechSynthesis())
      act(() => result.current.speak('hello'))
      expect(result.current.speaking).toBe(true)

      const onEnd = speakNative.mock.calls[0][1].onEnd
      act(() => onEnd())

      expect(result.current.speaking).toBe(false)
    })
  })

  describe('on the web (non-native)', () => {
    beforeEach(() => {
      isNativeTtsSupported.mockReturnValue(false)
    })

    it('reports supported via the Web Speech API and dispatches speak() to it', () => {
      isSpeechSynthesisSupported.mockReturnValue(true)
      const { result } = renderHook(() => useSpeechSynthesis())
      expect(result.current.supported).toBe(true)

      act(() => result.current.speak('hi'))

      expect(speak).toHaveBeenCalledTimes(1)
      expect(speak).toHaveBeenCalledWith('hi', { onEnd: expect.any(Function) })
      expect(speakNative).not.toHaveBeenCalled()
    })

    it('dispatches cancel() to the Web Speech API', () => {
      isSpeechSynthesisSupported.mockReturnValue(true)
      const { result } = renderHook(() => useSpeechSynthesis())
      act(() => result.current.cancel())

      expect(cancelSpeech).toHaveBeenCalledTimes(1)
      expect(cancelNativeSpeech).not.toHaveBeenCalled()
    })

    it('reports unsupported when neither native nor the Web Speech API is available', () => {
      isSpeechSynthesisSupported.mockReturnValue(false)
      const { result } = renderHook(() => useSpeechSynthesis())

      expect(result.current.supported).toBe(false)

      act(() => result.current.speak('should be a no-op'))

      expect(speak).not.toHaveBeenCalled()
      expect(speakNative).not.toHaveBeenCalled()
      expect(result.current.speaking).toBe(false)
    })
  })

  it('ignores a stale onEnd from an utterance that was already cancelled', () => {
    isNativeTtsSupported.mockReturnValue(false)
    isSpeechSynthesisSupported.mockReturnValue(true)
    const { result } = renderHook(() => useSpeechSynthesis())

    act(() => result.current.speak('first'))
    const staleOnEnd = speak.mock.calls[0][1].onEnd

    act(() => result.current.cancel())
    expect(result.current.speaking).toBe(false)

    // The first utterance's onEnd arrives late (after cancel) — it must not
    // resurrect `speaking`.
    act(() => staleOnEnd())
    expect(result.current.speaking).toBe(false)
  })
})
