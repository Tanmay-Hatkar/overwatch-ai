/**
 * CommitmentList.test.jsx — Covers the reminder_phrase edit affordance
 * (A2 of the AI-foundation plan): reminder_phrase previously had no edit
 * UI anywhere despite being the PRD's named "You said you'd..." mechanic
 * (ADR-0021) and the backend already accepting it via PATCH.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

vi.mock('../api', () => ({
  updateCommitment: vi.fn(() => Promise.resolve({})),
  deleteCommitment: vi.fn(() => Promise.resolve()),
}))
vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

import { updateCommitment } from '../api'
import CommitmentList from './CommitmentList'

function makeCommitment(overrides = {}) {
  return {
    id: 'c1',
    text: 'Call mom',
    due_at: null,
    status: 'open',
    recurrence: 'none',
    reminder_lead_minutes: 0,
    reminder_phrase: null,
    group_name: '',
    ...overrides,
  }
}

describe('CommitmentList — reminder_phrase edit affordance', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows a read-only preview when reminder_phrase is set', () => {
    const c = makeCommitment({ reminder_phrase: "You said you'd call mom — calling now?" })
    render(<CommitmentList commitments={[c]} onChange={vi.fn()} />)

    expect(screen.getByText(/You said you'd call mom/)).toBeInTheDocument()
  })

  it('shows no preview line when reminder_phrase is null', () => {
    const c = makeCommitment({ reminder_phrase: null })
    render(<CommitmentList commitments={[c]} onChange={vi.fn()} />)

    expect(screen.queryByText(/🔔/)).not.toBeInTheDocument()
  })

  it('clicking the commitment reveals an editable reminder_phrase field pre-filled with the current value', () => {
    const c = makeCommitment({ reminder_phrase: "You said you'd call mom — calling now?" })
    render(<CommitmentList commitments={[c]} onChange={vi.fn()} />)

    fireEvent.click(screen.getByText('Call mom'))

    const phraseInput = screen.getByPlaceholderText(/You said you'd call mom at 3pm/)
    expect(phraseInput.value).toBe("You said you'd call mom — calling now?")
  })

  it('editing the phrase and leaving the group saves reminder_phrase via PATCH', async () => {
    const onChange = vi.fn()
    const c = makeCommitment({ reminder_phrase: 'old phrase' })
    render(<CommitmentList commitments={[c]} onChange={onChange} />)

    fireEvent.click(screen.getByText('Call mom'))
    const phraseInput = screen.getByPlaceholderText(/You said you'd call mom at 3pm/)
    fireEvent.change(phraseInput, { target: { value: 'new better phrase' } })
    fireEvent.blur(phraseInput, { relatedTarget: document.body })

    await waitFor(() => {
      expect(updateCommitment).toHaveBeenCalledWith('c1', { reminder_phrase: 'new better phrase' })
    })
    expect(onChange).toHaveBeenCalled()
  })

  it('clearing the phrase saves reminder_phrase as null, not an empty string', async () => {
    const c = makeCommitment({ reminder_phrase: 'old phrase' })
    render(<CommitmentList commitments={[c]} onChange={vi.fn()} />)

    fireEvent.click(screen.getByText('Call mom'))
    const phraseInput = screen.getByPlaceholderText(/You said you'd call mom at 3pm/)
    fireEvent.change(phraseInput, { target: { value: '   ' } })
    fireEvent.blur(phraseInput, { relatedTarget: document.body })

    await waitFor(() => {
      expect(updateCommitment).toHaveBeenCalledWith('c1', { reminder_phrase: null })
    })
  })

  it('tabbing from the text field to the phrase field does not save prematurely', () => {
    const c = makeCommitment({ text: 'Call mom', reminder_phrase: 'old phrase' })
    render(<CommitmentList commitments={[c]} onChange={vi.fn()} />)

    fireEvent.click(screen.getByText('Call mom'))
    const textInput = screen.getByDisplayValue('Call mom')
    const phraseInput = screen.getByPlaceholderText(/You said you'd call mom at 3pm/)

    // Blur moving focus to a sibling within the same edit group must not commit.
    fireEvent.blur(textInput, { relatedTarget: phraseInput })

    expect(updateCommitment).not.toHaveBeenCalled()
  })

  it('does not call PATCH at all when nothing changed and focus leaves the group', async () => {
    const c = makeCommitment({ text: 'Call mom', reminder_phrase: 'old phrase' })
    render(<CommitmentList commitments={[c]} onChange={vi.fn()} />)

    fireEvent.click(screen.getByText('Call mom'))
    const phraseInput = screen.getByPlaceholderText(/You said you'd call mom at 3pm/)
    fireEvent.blur(phraseInput, { relatedTarget: document.body })

    // Give any pending microtask a chance to run, then assert nothing fired.
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(updateCommitment).not.toHaveBeenCalled()
  })
})
