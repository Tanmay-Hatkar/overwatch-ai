/**
 * ChatScreen.openClarify.test.js — one scenario per file deliberately;
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
  it('does not render chips for clarify_kind "open" (no fixed options)', async () => {
    sendChatMessage.mockResolvedValueOnce({
      reply: 'Sure — what time, and how long should I block?',
      intent: 'clarify',
      commitment: null,
      clarify_kind: 'open',
      clarify_options: null,
    })

    const screen = await render(<ChatScreen navigation={navigation} />)
    await waitFor(() => screen.getByPlaceholderText('Talk to Overwatch…'))
    await sendViaInput(screen, 'add a team meeting tomorrow')

    await waitFor(() => {
      expect(screen.getByText(/what time, and how long/)).toBeTruthy()
    })
  })
})
