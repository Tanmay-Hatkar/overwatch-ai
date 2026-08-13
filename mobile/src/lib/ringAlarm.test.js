/**
 * ringAlarm.test.js — covers the Tier-2 reconcile logic in ringAlarm.js.
 * Pure JS + mocked native module calls, no component rendering involved.
 *
 * Mock factories are deliberately fully inline (no outer `const mockX =
 * jest.fn()` referenced from inside them) -- see notifications.test.js's
 * header comment for why. Platform is mocked to 'android' since jest-expo
 * defaults the test platform to 'ios', and ringAlarm.js is Android-only.
 */
import { describe, it, expect, jest, beforeEach } from '@jest/globals'

jest.mock('react-native', () => ({
  Platform: { OS: 'android' },
}))

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(() => Promise.resolve(null)),
  setItemAsync: jest.fn(() => Promise.resolve()),
}))

jest.mock('../../modules/ring-alarm', () => ({
  __esModule: true,
  default: {
    ring: jest.fn(() => Promise.resolve()),
    cancelRing: jest.fn(() => Promise.resolve()),
    checkFullScreenIntentPermission: jest.fn(() => Promise.resolve(true)),
    openFullScreenIntentSettings: jest.fn(() => Promise.resolve()),
    drainPendingRingActions: jest.fn(() => Promise.resolve([])),
    addListener: jest.fn(() => ({ remove: jest.fn() })),
  },
}))

jest.mock('./notifications', () => ({
  notifId: jest.fn((id) => `reminder:${id}`),
  applyReminderAction: jest.fn(() => Promise.resolve()),
}))

import * as SecureStore from 'expo-secure-store'
import RingAlarm from '../../modules/ring-alarm'
import { applyReminderAction } from './notifications'
import {
  ESCALATE_AFTER_MINUTES,
  isRingEscalationEnabled,
  setRingEscalationEnabled,
  reconcileRingAlarms,
  cancelRing,
  initRingActionListener,
} from './ringAlarm'

function commitment(overrides = {}) {
  return {
    id: 'c1',
    text: 'Call mom',
    status: 'open',
    due_at: null,
    reminder_phrase: null,
    ...overrides,
  }
}

describe('isRingEscalationEnabled', () => {
  beforeEach(() => jest.clearAllMocks())

  it('defaults to enabled when nothing has been stored yet', async () => {
    SecureStore.getItemAsync.mockResolvedValueOnce(null)
    expect(await isRingEscalationEnabled()).toBe(true)
  })

  it('respects a persisted false value', async () => {
    SecureStore.getItemAsync.mockResolvedValueOnce('false')
    expect(await isRingEscalationEnabled()).toBe(false)
  })

  it('setRingEscalationEnabled persists the toggle', async () => {
    await setRingEscalationEnabled(false)
    expect(SecureStore.setItemAsync).toHaveBeenCalledWith('ow.ring.enabled', 'false')
  })
})

describe('reconcileRingAlarms', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    SecureStore.getItemAsync.mockResolvedValue(null)
  })

  it('schedules a ring ESCALATE_AFTER_MINUTES after due_at for an open commitment', async () => {
    const dueAt = new Date('2026-05-13T17:00:00Z')
    await reconcileRingAlarms([commitment({ due_at: dueAt.toISOString() })])

    expect(RingAlarm.ring).toHaveBeenCalledTimes(1)
    const [, commitmentId, title, body, atMillis] = RingAlarm.ring.mock.calls[0]
    expect(commitmentId).toBe('c1')
    expect(title).toBe('Overwatch')
    expect(body).toBe('Still pending: Call mom')
    expect(atMillis).toBe(dueAt.getTime() + ESCALATE_AFTER_MINUTES * 60_000)
  })

  it('uses reminder_phrase as the body when present', async () => {
    await reconcileRingAlarms([
      commitment({ due_at: new Date().toISOString(), reminder_phrase: "You said you'd call mom" }),
    ])
    const [, , , body] = RingAlarm.ring.mock.calls[0]
    expect(body).toBe("You said you'd call mom")
  })

  it('skips commitments with no due date', async () => {
    await reconcileRingAlarms([commitment({ due_at: null })])
    expect(RingAlarm.ring).not.toHaveBeenCalled()
  })

  it('skips done commitments', async () => {
    await reconcileRingAlarms([commitment({ due_at: new Date().toISOString(), status: 'done' })])
    expect(RingAlarm.ring).not.toHaveBeenCalled()
  })

  it('schedules nothing when escalation is disabled', async () => {
    SecureStore.getItemAsync.mockResolvedValue('false')
    await reconcileRingAlarms([commitment({ due_at: new Date().toISOString() })])
    expect(RingAlarm.ring).not.toHaveBeenCalled()
  })

  it('cancels a previously scheduled id that is no longer in the new set', async () => {
    SecureStore.getItemAsync.mockImplementation((key) =>
      Promise.resolve(key === 'ow.ring.scheduledIds' ? '[999]' : null),
    )
    await reconcileRingAlarms([])
    expect(RingAlarm.cancelRing).toHaveBeenCalledWith(999)
  })
})

describe('cancelRing', () => {
  beforeEach(() => jest.clearAllMocks())

  it('delegates to the native module', async () => {
    await cancelRing(42)
    expect(RingAlarm.cancelRing).toHaveBeenCalledWith(42)
  })
})

describe('initRingActionListener', () => {
  beforeEach(() => jest.clearAllMocks())

  it('registers a ringAction listener and drains queued actions through applyReminderAction', async () => {
    RingAlarm.drainPendingRingActions.mockResolvedValueOnce([
      { id: 7, commitmentId: 'c2', action: 'DONE' },
    ])

    const unsubscribe = initRingActionListener()
    expect(RingAlarm.addListener).toHaveBeenCalledWith('ringAction', expect.any(Function))

    // flush the drainPendingRingActions().then(...) microtask
    await Promise.resolve()
    await Promise.resolve()

    expect(applyReminderAction).toHaveBeenCalledWith('DONE', { id: 'reminder:c2', commitmentId: 'c2' })

    unsubscribe()
  })

  it('forwards a live ringAction event through applyReminderAction', () => {
    initRingActionListener()
    const liveHandler = RingAlarm.addListener.mock.calls[0][1]
    liveHandler({ id: 7, commitmentId: 'c3', action: 'SNOOZE' })
    expect(applyReminderAction).toHaveBeenCalledWith('SNOOZE', { id: 'reminder:c3', commitmentId: 'c3' })
  })
})
