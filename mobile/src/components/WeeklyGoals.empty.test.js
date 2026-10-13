/**
 * WeeklyGoals.empty.test.js — no goals yet: a single quiet invitation row.
 */
import { describe, it, expect, jest } from '@jest/globals'
import { fireEvent, render } from '@testing-library/react-native'
import WeeklyGoals from './WeeklyGoals'

describe('WeeklyGoals (empty)', () => {
  it('shows one add row and no section header', async () => {
    const onAdd = jest.fn()
    const screen = await render(
      <WeeklyGoals goals={[]} onLog={jest.fn()} onOpen={jest.fn()} onDecide={jest.fn()} onAdd={onAdd} />,
    )
    expect(screen.queryByText('This week')).toBeNull()
    fireEvent.press(screen.getByLabelText('Add a weekly goal'))
    expect(onAdd).toHaveBeenCalled()
  })
})
