/**
 * UpNextCard.earlier.test.js — the "slipped by" restart framing.
 * One render per file (see screens/chatScreenTestUtils.js).
 */
import { describe, it, expect } from '@jest/globals'
import { render } from '@testing-library/react-native'
import UpNextCard from './UpNextCard'

const NOW = new Date('2026-10-09T21:00:00')
const commitment = {
  id: 'c2',
  text: 'Call mom',
  status: 'open',
  due_at: new Date(NOW.getTime() - 3 * 3600e3).toISOString(),
  reminder_phrase: "You said you'd call mom — still on?",
}

describe('UpNextCard (earlier)', () => {
  it('asks "still on?" without judgment language', async () => {
    const noop = () => {}
    const screen = await render(
      <UpNextCard focus={{ commitment, kind: 'earlier' }} now={NOW} onDone={noop} onMove={noop} onTalk={noop} />,
    )

    expect(screen.getByText('STILL ON?')).toBeTruthy()
    expect(screen.getByText(/3 hr ago/)).toBeTruthy()
    expect(screen.queryByText(/overdue/i)).toBeNull()
  })
})
