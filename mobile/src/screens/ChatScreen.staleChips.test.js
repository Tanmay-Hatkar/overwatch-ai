/**
 * ChatScreen.staleChips.test.js — one scenario per file deliberately;
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
  it('does not render chips on an older turn once the conversation has moved on', async () => {
    sendChatMessage.mockResolvedValueOnce({
      reply: 'Repeat daily?',
      intent: 'clarify',
      commitment: null,
      clarify_kind: 'confirm_recurring',
      clarify_options: ['Yes', 'No'],
    })
    sendChatMessage.mockResolvedValueOnce({
      reply: 'Got it.',
      intent: 'general',
      commitment: null,
    })

    const screen = await render(<ChatScreen navigation={navigation} />)
    await waitFor(() => screen.getByPlaceholderText('Talk to Overwatch…'))
    await sendViaInput(screen, 'add it to my routine')
    await waitFor(() => screen.getByText('Yes'))

    await sendViaInput(screen, 'yes please')

    await waitFor(() => expect(screen.getByText('Got it.')).toBeTruthy())
    expect(screen.queryByText('Yes')).toBeNull()
  })
})
