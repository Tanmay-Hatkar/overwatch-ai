/**
 * UpNextCard.upcoming.test.js — one render per file, matching the
 * convention in screens/chatScreenTestUtils.js.
 */
import { describe, it, expect, jest } from '@jest/globals'
import { fireEvent, render } from '@testing-library/react-native'
import UpNextCard from './UpNextCard'

const NOW = new Date('2026-10-09T21:00:00')
const commitment = {
  id: 'c1',
  text: 'Finish GenAI interview prep',
  status: 'open',
  due_at: new Date(NOW.getTime() + 45 * 60000).toISOString(),
  reminder_phrase: "You said you'd finish interview prep — starting?",
}

describe('UpNextCard (upcoming)', () => {
  it('shows the countdown and reminder line, and wires the actions', async () => {
    const onDone = jest.fn()
    const onMove = jest.fn()
    const onTalk = jest.fn()
    const screen = await render(
      <UpNextCard
        focus={{ commitment, kind: 'upcoming' }}
        now={NOW}
        onDone={onDone}
        onMove={onMove}
        onTalk={onTalk}
      />,
    )

    expect(screen.getByText('UP NEXT')).toBeTruthy()
    expect(screen.getByText(/in 45 min/)).toBeTruthy()
    expect(screen.getByText(commitment.reminder_phrase)).toBeTruthy()

    fireEvent.press(screen.getByLabelText('Mark Finish GenAI interview prep done'))
    fireEvent.press(screen.getByLabelText('Move Finish GenAI interview prep'))
    fireEvent.press(screen.getByLabelText('Talk it through in chat'))
    expect(onDone).toHaveBeenCalledWith(commitment)
    expect(onMove).toHaveBeenCalledWith(commitment)
    expect(onTalk).toHaveBeenCalled()
  })
})
