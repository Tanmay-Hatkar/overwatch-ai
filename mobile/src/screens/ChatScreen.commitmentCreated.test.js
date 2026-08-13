/**
 * ChatScreen.commitmentCreated.test.js — one scenario per file
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
  it('shows a confirmation tag when a commitment is created', async () => {
    sendChatMessage.mockResolvedValueOnce({
      reply: 'Got it — calling mom Wednesday at 3pm.',
      intent: 'add_commitment',
      commitment: { id: 'c1', text: 'Call mom' },
    })

    const screen = await render(<ChatScreen navigation={navigation} />)
    await waitFor(() => screen.getByPlaceholderText('Talk to Overwatch…'))
    await sendViaInput(screen, 'call mom tomorrow at 3pm')

    await waitFor(() => {
      expect(screen.getByText('✓ Added: Call mom')).toBeTruthy()
    })
  })
})
