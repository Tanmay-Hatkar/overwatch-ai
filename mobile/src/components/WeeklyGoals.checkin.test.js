/**
 * WeeklyGoals.checkin.test.js — a goal in the end-of-week check-in state.
 * One render per file, matching the convention in screens/chatScreenTestUtils.js.
 */
import { describe, it, expect, jest } from '@jest/globals'
import { fireEvent, render } from '@testing-library/react-native'
import WeeklyGoals from './WeeklyGoals'

const goal = {
  id: 'g1',
  text: 'Job applications',
  target_count: 10,
  done_this_week: 6,
  remaining: 4,
  days_left: 2,
  state: 'check_in',
  week_start: '2026-10-12',
}

describe('WeeklyGoals (check-in)', () => {
  it('shows progress, logs +1, and offers the three check-in answers', async () => {
    const onLog = jest.fn()
    const onOpen = jest.fn()
    const onDecide = jest.fn()
    const screen = await render(
      <WeeklyGoals goals={[goal]} onLog={onLog} onOpen={onOpen} onDecide={onDecide} onAdd={jest.fn()} />,
    )

    expect(screen.getByText('This week')).toBeTruthy()
    expect(screen.getByText('4 to go · 2 days left')).toBeTruthy()
    expect(screen.getByText(/call this week good\?/)).toBeTruthy()

    fireEvent.press(screen.getByLabelText('Log one for Job applications'))
    expect(onLog).toHaveBeenCalledWith(goal)

    fireEvent.press(screen.getByLabelText('Keep going'))
    fireEvent.press(screen.getByLabelText('Call it good'))
    expect(onDecide).toHaveBeenNthCalledWith(1, goal, 'keep_going')
    expect(onDecide).toHaveBeenNthCalledWith(2, goal, 'call_it_good')

    fireEvent.press(screen.getByLabelText('Adjust'))
    expect(onOpen).toHaveBeenCalledWith(goal)
  })
})
