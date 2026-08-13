/**
 * ChatBar.test.jsx — Covers the structured clarify chip rendering (A3 of
 * the AI-foundation plan): a clarify reply with clarify_options used to
 * render identically to any other chat bubble, forcing the user to type a
 * free-text answer into the same box. Now it renders tap-only chips that
 * send the exact option text as the next message.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

vi.mock('../api', () => ({
  sendChat: vi.fn(),
  getChatHistory: vi.fn(() => Promise.resolve([])),
  clearChatHistory: vi.fn(() => Promise.resolve()),
}))
vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))
vi.mock('../hooks/useSpeechRecognition', () => ({
  useSpeechRecognition: () => ({
    supported: false,
    listening: false,
    error: null,
    start: vi.fn(),
    stop: vi.fn(),
  }),
}))
vi.mock('../hooks/useSpeechSynthesis', () => ({
  useSpeechSynthesis: () => ({
    supported: false,
    speak: vi.fn(),
    cancel: vi.fn(),
  }),
}))

import { sendChat } from '../api'
import ChatBar from './ChatBar'

// jsdom doesn't implement scrollIntoView; ChatBar calls it on every
// history update to keep the newest message in view.
Element.prototype.scrollIntoView = vi.fn()

async function sendMessageViaInput(text) {
  const input = screen.getByPlaceholderText('Talk to Overwatch…')
  fireEvent.change(input, { target: { value: text } })
  fireEvent.submit(input.closest('form'))
}

describe('ChatBar — structured clarify chips', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  it('renders tap-only chips for a clarify reply with clarify_options', async () => {
    sendChat.mockResolvedValueOnce({
      reply: "Got it — want 'Start Night Routine' to repeat every day?",
      intent: 'clarify',
      commitment: null,
      clarify_kind: 'confirm_recurring',
      clarify_options: ['Yes, daily', 'No, just once'],
    })

    render(<ChatBar />)
    await sendMessageViaInput('add it to my routine')

    await waitFor(() => {
      expect(screen.getByText('Yes, daily')).toBeInTheDocument()
      expect(screen.getByText('No, just once')).toBeInTheDocument()
    })
  })

  it('tapping a chip sends its exact label as the next message', async () => {
    sendChat.mockResolvedValueOnce({
      reply: "Got it — want 'Start Night Routine' to repeat every day?",
      intent: 'clarify',
      commitment: null,
      clarify_kind: 'confirm_recurring',
      clarify_options: ['Yes, daily', 'No, just once'],
    })
    sendChat.mockResolvedValueOnce({
      reply: 'Set to repeat daily.',
      intent: 'add_commitment',
      commitment: { id: 'c1', text: 'Start night routine' },
    })

    render(<ChatBar />)
    await sendMessageViaInput('add it to my routine')
    await waitFor(() => expect(screen.getByText('Yes, daily')).toBeInTheDocument())

    fireEvent.click(screen.getByText('Yes, daily'))

    await waitFor(() => {
      expect(sendChat).toHaveBeenCalledTimes(2)
      expect(sendChat.mock.calls[1][0]).toBe('Yes, daily')
    })
  })

  it('does not render chips for clarify_kind "open" (no fixed options)', async () => {
    sendChat.mockResolvedValueOnce({
      reply: 'Sure — what time, and how long should I block?',
      intent: 'clarify',
      commitment: null,
      clarify_kind: 'open',
      clarify_options: null,
    })

    render(<ChatBar />)
    await sendMessageViaInput('add a team meeting tomorrow')

    await waitFor(() => {
      expect(screen.getByText(/what time, and how long/)).toBeInTheDocument()
    })
    expect(screen.queryByRole('button', { name: /yes|no/i })).not.toBeInTheDocument()
  })

  it('does not render chips on an older turn once the conversation has moved on', async () => {
    sendChat.mockResolvedValueOnce({
      reply: 'Repeat daily?',
      intent: 'clarify',
      commitment: null,
      clarify_kind: 'confirm_recurring',
      clarify_options: ['Yes', 'No'],
    })
    sendChat.mockResolvedValueOnce({
      reply: 'Got it.',
      intent: 'general',
      commitment: null,
    })

    render(<ChatBar />)
    await sendMessageViaInput('add it to my routine')
    await waitFor(() => expect(screen.getByText('Yes')).toBeInTheDocument())

    // Answer via typing instead of tapping — the clarify turn is no longer latest.
    await sendMessageViaInput('yes please')

    await waitFor(() => expect(screen.getByText('Got it.')).toBeInTheDocument())
    expect(screen.queryByText('Yes')).not.toBeInTheDocument()
  })
})
