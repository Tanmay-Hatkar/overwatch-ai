/**
 * ChatScreen.chipTap.test.js — one scenario per file deliberately;
 * see chatScreenTestUtils.js for why.
 */
import { describe, it, expect, jest } from '@jest/globals'
import { render, fireEvent, waitFor, act } from '@testing-library/react-native'

jest.mock('../api', () => ({
  sendChatMessage: jest.fn(),
  getChatHistory: jest.fn(() => Promise.resolve([])),
}))

import { sendChatMessage } from '../api'
import ChatScreen from './ChatScreen'
import { navigation, sendViaInput } from './chatScreenTestUtils'

describe('ChatScreen — structured clarify chips', () => {
  it('tapping a chip sends its exact label as the next message', async () => {
    sendChatMessage.mockResolvedValueOnce({
      reply: 'Repeat every day?',
      intent: 'clarify',
      commitment: null,
      clarify_kind: 'confirm_recurring',
      clarify_options: ['Yes, daily', 'No, just once'],
    })
    sendChatMessage.mockResolvedValueOnce({
      reply: 'Set to repeat daily.',
      intent: 'add_commitment',
      commitment: { id: 'c1', text: 'Start night routine' },
    })

    const screen = await render(<ChatScreen navigation={navigation} />)
    await waitFor(() => screen.getByPlaceholderText('Talk to Overwatch…'))
    await sendViaInput(screen, 'add it to my routine')
    await waitFor(() => screen.getByText('Yes, daily'))

    await act(async () => {})
    fireEvent.press(screen.getByTestId('clarify-chip-Yes, daily'))

    await waitFor(() => {
      expect(sendChatMessage).toHaveBeenCalledTimes(2)
      expect(sendChatMessage.mock.calls[1][0]).toBe('Yes, daily')
    })
  })
})
