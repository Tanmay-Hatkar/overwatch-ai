/**
 * api.test.js — covers the chat/briefing/reflection additions to the API
 * client. Mocks global.fetch and SecureStore directly rather than relying
 * on jest-expo's auto-mocks, so the request shape (method, body, auth
 * header) is asserted explicitly against what the backend actually expects.
 */
import { describe, it, expect, jest, beforeEach } from '@jest/globals'

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(() => Promise.resolve('test-token')),
  setItemAsync: jest.fn(() => Promise.resolve()),
  deleteItemAsync: jest.fn(() => Promise.resolve()),
}))

jest.mock('expo-constants', () => ({
  __esModule: true,
  default: { expoConfig: { extra: { apiBaseUrl: 'https://api.test' } } },
}))

// auth.js mirrors token writes into the home-screen widget's native config
// store (ADR-0020) -- mocked here since api.js -> auth.js -> widget.js pulls
// in the real native module, which throws in the jest-expo test environment.
jest.mock('../modules/widget', () => ({
  __esModule: true,
  default: {
    configure: jest.fn(() => Promise.resolve()),
    clear: jest.fn(() => Promise.resolve()),
    refreshNow: jest.fn(() => Promise.resolve()),
  },
}))

import {
  sendChatMessage,
  getChatHistory,
  clearChatHistory,
  getMorningBriefing,
  getEveningReflection,
} from './api'

function mockFetchOnce(body, { status = 200 } = {}) {
  global.fetch = jest.fn(() =>
    Promise.resolve({
      ok: status < 400,
      status,
      statusText: 'OK',
      json: () => Promise.resolve(body),
    }),
  )
}

describe('api.js — chat', () => {
  beforeEach(() => jest.clearAllMocks())

  it('sendChatMessage POSTs to /chat with message, history, timezone, and bearer auth', async () => {
    mockFetchOnce({ reply: 'Got it.', intent: 'general', commitment: null })

    await sendChatMessage('hi', [{ role: 'user', content: 'earlier' }], 'America/Toronto')

    expect(global.fetch).toHaveBeenCalledTimes(1)
    const [url, options] = global.fetch.mock.calls[0]
    expect(url).toBe('https://api.test/chat')
    expect(options.method).toBe('POST')
    expect(options.headers.Authorization).toBe('Bearer test-token')
    expect(JSON.parse(options.body)).toEqual({
      message: 'hi',
      history: [{ role: 'user', content: 'earlier' }],
      timezone: 'America/Toronto',
    })
  })

  it('sendChatMessage returns clarify_kind/clarify_options through untouched', async () => {
    mockFetchOnce({
      reply: 'Repeat every day?',
      intent: 'clarify',
      commitment: null,
      clarify_kind: 'confirm_recurring',
      clarify_options: ['Yes, daily', 'No, just once'],
    })

    const result = await sendChatMessage('add it to my routine')

    expect(result.clarify_kind).toBe('confirm_recurring')
    expect(result.clarify_options).toEqual(['Yes, daily', 'No, just once'])
  })

  it('getChatHistory GETs /chat/history with a limit param', async () => {
    mockFetchOnce([])
    await getChatHistory(10)
    expect(global.fetch.mock.calls[0][0]).toBe('https://api.test/chat/history?limit=10')
  })

  it('clearChatHistory DELETEs /chat/history', async () => {
    global.fetch = jest.fn(() => Promise.resolve({ ok: true, status: 204 }))
    await clearChatHistory()
    expect(global.fetch.mock.calls[0][1].method).toBe('DELETE')
  })
})

describe('api.js — briefings & reflections', () => {
  beforeEach(() => jest.clearAllMocks())

  it('getMorningBriefing GETs /briefings/today with the device timezone by default', async () => {
    mockFetchOnce({ content: 'x', today_count: 0, overdue_count: 0, cached: false })
    await getMorningBriefing()
    const url = global.fetch.mock.calls[0][0]
    expect(url).toMatch(/^https:\/\/api\.test\/briefings\/today\?timezone=/)
  })

  it('getMorningBriefing sets force_regenerate when requested', async () => {
    mockFetchOnce({ content: 'x' })
    await getMorningBriefing({ forceRegenerate: true, timezone: 'UTC' })
    const url = global.fetch.mock.calls[0][0]
    expect(url).toBe('https://api.test/briefings/today?force_regenerate=true&timezone=UTC')
  })

  it('getEveningReflection GETs /reflections/today', async () => {
    mockFetchOnce({ content: 'x' })
    await getEveningReflection({ timezone: 'UTC' })
    expect(global.fetch.mock.calls[0][0]).toBe('https://api.test/reflections/today?timezone=UTC')
  })
})
