import { describe, it, expect } from '@jest/globals'
import { getDeviceTimezone } from './timezone'

describe('getDeviceTimezone', () => {
  it('returns a non-empty IANA-shaped string in a normal environment', () => {
    const tz = getDeviceTimezone()
    expect(typeof tz).toBe('string')
    expect(tz.length).toBeGreaterThan(0)
  })

  it('returns null instead of throwing if Intl is unavailable', () => {
    const original = global.Intl
    // @ts-expect-error deliberately breaking Intl to test the fallback
    global.Intl = undefined
    try {
      expect(getDeviceTimezone()).toBeNull()
    } finally {
      global.Intl = original
    }
  })
})
