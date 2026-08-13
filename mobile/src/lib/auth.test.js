/**
 * auth.test.js — covers secure-token storage plus the widget-config
 * mirroring wired in alongside it (ADR-0020). Mock factories are fully
 * inline; see ringAlarm.test.js's header comment for why.
 */
import { describe, it, expect, jest, beforeEach } from '@jest/globals'

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(() => Promise.resolve(null)),
  setItemAsync: jest.fn(() => Promise.resolve()),
  deleteItemAsync: jest.fn(() => Promise.resolve()),
}))

jest.mock('./widget', () => ({
  configureWidget: jest.fn(() => Promise.resolve()),
  clearWidget: jest.fn(() => Promise.resolve()),
}))

import * as SecureStore from 'expo-secure-store'
import { configureWidget, clearWidget } from './widget'
import { getStoredToken, setStoredToken, clearStoredToken } from './auth'

describe('getStoredToken', () => {
  beforeEach(() => jest.clearAllMocks())

  it('returns null when never signed in', async () => {
    SecureStore.getItemAsync.mockResolvedValueOnce(null)
    expect(await getStoredToken()).toBeNull()
  })

  it('returns the stored token', async () => {
    SecureStore.getItemAsync.mockResolvedValueOnce('tok-123')
    expect(await getStoredToken()).toBe('tok-123')
  })
})

describe('setStoredToken', () => {
  beforeEach(() => jest.clearAllMocks())

  it('persists the token and mirrors it to the widget', async () => {
    await setStoredToken('tok-123')
    expect(SecureStore.setItemAsync).toHaveBeenCalledWith('ow.session.token', 'tok-123')
    expect(configureWidget).toHaveBeenCalledWith('tok-123')
  })
})

describe('clearStoredToken', () => {
  beforeEach(() => jest.clearAllMocks())

  it('deletes the token and clears the widget', async () => {
    await clearStoredToken()
    expect(SecureStore.deleteItemAsync).toHaveBeenCalledWith('ow.session.token')
    expect(clearWidget).toHaveBeenCalledTimes(1)
  })
})
