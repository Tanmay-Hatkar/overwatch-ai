/**
 * widget.test.js — covers the JS-side handoff to the native widget module.
 * Platform is mocked to 'android' since jest-expo defaults the test
 * platform to 'ios' and widget.js is Android-only. See ringAlarm.test.js's
 * header comment for why mock factories are fully inline here.
 */
import { describe, it, expect, jest, beforeEach } from '@jest/globals'

jest.mock('react-native', () => ({
  Platform: { OS: 'android' },
}))

jest.mock('expo-constants', () => ({
  __esModule: true,
  default: { expoConfig: { extra: { apiBaseUrl: 'https://api.example.com' } } },
}))

jest.mock('../../modules/widget', () => ({
  __esModule: true,
  default: {
    configure: jest.fn(() => Promise.resolve()),
    clear: jest.fn(() => Promise.resolve()),
    refreshNow: jest.fn(() => Promise.resolve()),
  },
}))

import Widget from '../../modules/widget'
import { configureWidget, clearWidget } from './widget'

describe('configureWidget', () => {
  beforeEach(() => jest.clearAllMocks())

  it('passes the API base URL and token to the native module', async () => {
    await configureWidget('tok-123')
    expect(Widget.configure).toHaveBeenCalledWith('https://api.example.com', 'tok-123')
  })

  it('does nothing when there is no token', async () => {
    await configureWidget(null)
    expect(Widget.configure).not.toHaveBeenCalled()
  })
})

describe('clearWidget', () => {
  beforeEach(() => jest.clearAllMocks())

  it('delegates to the native module', async () => {
    await clearWidget()
    expect(Widget.clear).toHaveBeenCalledTimes(1)
  })
})
