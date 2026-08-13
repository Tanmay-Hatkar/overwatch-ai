/**
 * ChatScreen.clarifyChips.test.js — one scenario per file deliberately;
 * see chatScreenTestUtils.js for why.
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
  it('renders tap-only chips for a clarify reply with clarify_options', async () => {
    sendChatMessage.mockResolvedValueOnce({
      reply: "Got it — want 'Start Night Routine' to repeat every day?",
      intent: 'clarify',
      commitment: null,
      clarify_kind: 'confirm_recurring',
      clarify_options: ['Yes, daily', 'No, just once'],
    })

    const screen = await render(<ChatScreen navigation={navigation} />)
    await waitFor(() => screen.getByPlaceholderText('Talk to Overwatch…'))
    await sendViaInput(screen, 'add it to my routine')

    await waitFor(() => {
      expect(screen.getByText('Yes, daily')).toBeTruthy()
      expect(screen.getByText('No, just once')).toBeTruthy()
    })
  })
})
