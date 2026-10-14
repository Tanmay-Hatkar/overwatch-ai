/**
 * ChatScreen.commitmentClosed.test.js — one scenario per file
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

describe('ChatScreen — close_commitment', () => {
  it('shows a deleted tag naming every closed commitment', async () => {
    sendChatMessage.mockResolvedValueOnce({
      reply: "Deleted 'Do laundry' and 'Hit the gym'.",
      intent: 'close_commitment',
      close_action: 'deleted',
      closed: [
        { id: 'c5', text: 'Do laundry' },
        { id: 'c6', text: 'Hit the gym' },
      ],
    })

    const screen = await render(<ChatScreen navigation={navigation} />)
    await waitFor(() => screen.getByPlaceholderText('Talk to Overwatch…'))
    await sendViaInput(screen, 'delete the laundry and the gym ones')

    await waitFor(() => {
      expect(screen.getByText('🗑 Deleted: Do laundry, Hit the gym')).toBeTruthy()
    })
  })
})
