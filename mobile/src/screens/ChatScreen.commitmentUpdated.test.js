/**
 * ChatScreen.commitmentUpdated.test.js — one scenario per file
 * deliberately; see chatScreenTestUtils.js for why.
 */
import { describe, it, expect, jest } from '@jest/globals'
import { render, waitFor } from '@testing-library/react-native'

jest.mock('../api', () => ({
  sendChatMessage: jest.fn(),
  getChatHistory: jest.fn(() => Promise.resolve([])),
}))

import { sendChatMessage } from '../api'
import ChatScreen from './ChatScreen'
import { navigation, sendViaInput } from './chatScreenTestUtils'

describe('ChatScreen — structured clarify chips', () => {
  it('shows an updated tag when modify_commitment changes a commitment', async () => {
    sendChatMessage.mockResolvedValueOnce({
      reply: 'Moved to tomorrow at 5pm.',
      intent: 'modify_commitment',
      commitment: { id: 'c1', text: 'Finish the deck' },
    })

    const screen = await render(<ChatScreen navigation={navigation} />)
    await waitFor(() => screen.getByPlaceholderText('Talk to Overwatch…'))
    await sendViaInput(screen, 'push the deck to tomorrow at 5pm')

    await waitFor(() => {
      expect(screen.getByText('✏️ Updated: Finish the deck')).toBeTruthy()
    })
  })
})
