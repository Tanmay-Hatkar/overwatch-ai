/**
 * notifications.test.js — covers the reconcile logic ported from
 * frontend/src/lib/notifications.js. Pure JS + mocked expo-notifications
 * calls, no component rendering involved.
 *
 * The mock factory below is deliberately fully inline (no outer `const
 * mockX = jest.fn()` referenced from inside it) -- referencing an
 * externally-declared mock-prefixed variable from within jest.mock()'s
 * factory silently breaks in this project's babel/jest setup (the
 * factory's own inline jest.fn() calls work; closing over an outer one
 * doesn't, despite jest's "mock"-prefix hoisting exception normally
 * supporting exactly that pattern). Assertions instead go through the
 * mocked module's own namespace import, retrieved after jest.mock().
 */
import { describe, it, expect, jest, beforeEach } from '@jest/globals'

jest.mock('expo-notifications', () => ({
  scheduleNotificationAsync: jest.fn(() => Promise.resolve('id')),
  cancelAllScheduledNotificationsAsync: jest.fn(() => Promise.resolve()),
  setNotificationChannelAsync: jest.fn(() => Promise.resolve()),
  setNotificationCategoryAsync: jest.fn(() => Promise.resolve()),
  getPermissionsAsync: jest.fn(() => Promise.resolve({ granted: false })),
  requestPermissionsAsync: jest.fn(() => Promise.resolve({ granted: true })),
  addNotificationResponseReceivedListener: jest.fn(() => ({ remove: jest.fn() })),
  AndroidImportance: { HIGH: 4 },
  AndroidNotificationVisibility: { PUBLIC: 1 },
  SchedulableTriggerInputTypes: { DATE: 'date' },
}))

jest.mock('../api', () => ({
  updateCommitment: jest.fn(() => Promise.resolve()),
}))

import * as Notifications from 'expo-notifications'
import {
  notifId,
  staleCheckFireAt,
  syncCommitmentReminders,
  ensureNotificationPermission,
} from './notifications'

function commitment(overrides = {}) {
  return {
    id: 'c1',
    text: 'Call mom',
    status: 'open',
    due_at: null,
    reminder_lead_minutes: 0,
    reminder_phrase: null,
    stale_check_sent_at: null,
    updated_at: new Date().toISOString(),
    ...overrides,
  }
}

describe('notifId', () => {
  it('returns a stable, namespaced id per commitment', () => {
    expect(notifId('abc-123')).toBe('reminder:abc-123')
    expect(notifId('abc-123')).toBe(notifId('abc-123'))
  })
})

describe('staleCheckFireAt', () => {
  it('fires 4h after updated_at when there is no due_at', () => {
    const updatedAt = new Date('2026-05-12T10:00:00Z')
    const c = { due_at: null, updated_at: updatedAt.toISOString() }
    expect(staleCheckFireAt(c)).toBe(updatedAt.getTime() + 4 * 3_600_000)
  })

  it('is bound by the due date when it is further out than the dormancy window', () => {
    const updatedAt = new Date()
    const dueAt = new Date(Date.now() + 7 * 86_400_000) // a week out
    const c = { due_at: dueAt.toISOString(), updated_at: updatedAt.toISOString() }
    const dormantAt = updatedAt.getTime() + 4 * 3_600_000
    expect(staleCheckFireAt(c)).toBeGreaterThan(dormantAt)
  })

  it('uses dormancy as the binding constraint when the due date has already passed', () => {
    const updatedAt = new Date()
    const dueAt = new Date(Date.now() - 86_400_000) // yesterday
    const c = { due_at: dueAt.toISOString(), updated_at: updatedAt.toISOString() }
    expect(staleCheckFireAt(c)).toBe(updatedAt.getTime() + 4 * 3_600_000)
  })
})

describe('ensureNotificationPermission', () => {
  beforeEach(() => jest.clearAllMocks())

  it('returns true immediately if already granted, without re-requesting', async () => {
    Notifications.getPermissionsAsync.mockResolvedValueOnce({ granted: true })
    const result = await ensureNotificationPermission()
    expect(result).toBe(true)
    expect(Notifications.requestPermissionsAsync).not.toHaveBeenCalled()
  })

  it('requests permission when not already granted', async () => {
    Notifications.getPermissionsAsync.mockResolvedValueOnce({ granted: false })
    Notifications.requestPermissionsAsync.mockResolvedValueOnce({ granted: true })
    const result = await ensureNotificationPermission()
    expect(result).toBe(true)
    expect(Notifications.requestPermissionsAsync).toHaveBeenCalledTimes(1)
  })
})

describe('syncCommitmentReminders', () => {
  beforeEach(() => jest.clearAllMocks())

  it('cancels everything previously scheduled before rescheduling', async () => {
    await syncCommitmentReminders([])
    expect(Notifications.cancelAllScheduledNotificationsAsync).toHaveBeenCalledTimes(1)
  })

  it('schedules a reminder for an open commitment with a future due_at', async () => {
    const futureDue = new Date(Date.now() + 3_600_000).toISOString()
    await syncCommitmentReminders([commitment({ due_at: futureDue })])

    const call = Notifications.scheduleNotificationAsync.mock.calls.find(
      (c) => c[0].identifier === 'reminder:c1',
    )
    expect(call).toBeTruthy()
    expect(call[0].content.body).toBe('Time to start: Call mom')
  })

  it('uses reminder_phrase as the body when present', async () => {
    const futureDue = new Date(Date.now() + 3_600_000).toISOString()
    await syncCommitmentReminders([
      commitment({ due_at: futureDue, reminder_phrase: "You said you'd call mom — calling now?" }),
    ])

    const call = Notifications.scheduleNotificationAsync.mock.calls.find(
      (c) => c[0].identifier === 'reminder:c1',
    )
    expect(call[0].content.body).toBe("You said you'd call mom — calling now?")
  })

  it('does not schedule a reminder for a commitment with no due_at', async () => {
    await syncCommitmentReminders([commitment({ due_at: null })])
    const call = Notifications.scheduleNotificationAsync.mock.calls.find(
      (c) => c[0].identifier === 'reminder:c1',
    )
    expect(call).toBeUndefined()
  })

  it('does not schedule a reminder whose fire time has already passed', async () => {
    const pastDue = new Date(Date.now() - 3_600_000).toISOString()
    await syncCommitmentReminders([commitment({ due_at: pastDue })])
    const call = Notifications.scheduleNotificationAsync.mock.calls.find(
      (c) => c[0].identifier === 'reminder:c1',
    )
    expect(call).toBeUndefined()
  })

  it('skips done commitments entirely', async () => {
    const futureDue = new Date(Date.now() + 3_600_000).toISOString()
    await syncCommitmentReminders([commitment({ due_at: futureDue, status: 'done' })])
    expect(Notifications.scheduleNotificationAsync).not.toHaveBeenCalled()
  })

  it('schedules a stale-check notification for an open commitment never asked about', async () => {
    await syncCommitmentReminders([commitment({ stale_check_sent_at: null })])
    const call = Notifications.scheduleNotificationAsync.mock.calls.find(
      (c) => c[0].identifier === 'stale:c1',
    )
    expect(call).toBeTruthy()
    expect(call[0].content.body).toBe('Still the plan — "Call mom"? Or has today changed?')
  })

  it('does not schedule a stale-check for a commitment the server already asked about', async () => {
    await syncCommitmentReminders([commitment({ stale_check_sent_at: new Date().toISOString() })])
    const call = Notifications.scheduleNotificationAsync.mock.calls.find(
      (c) => c[0].identifier === 'stale:c1',
    )
    expect(call).toBeUndefined()
  })

  it('applies a positive reminder_lead_minutes as a heads-up before due_at', async () => {
    const futureDue = new Date(Date.now() + 3_600_000).toISOString()
    await syncCommitmentReminders([commitment({ due_at: futureDue, reminder_lead_minutes: 15 })])
    const call = Notifications.scheduleNotificationAsync.mock.calls.find(
      (c) => c[0].identifier === 'reminder:c1',
    )
    expect(call[0].content.body).toBe('In 15 min: Call mom')
  })
})
