import { describe, it, expect } from '@jest/globals'
import { sectionizeCommitments } from './sections'

function c(overrides = {}) {
  return { id: '1', text: 'Task', due_at: null, status: 'open', ...overrides }
}

describe('sectionizeCommitments', () => {
  it('buckets a commitment with no due_at into "No due date"', () => {
    const sections = sectionizeCommitments([c({ id: 'a' })])
    expect(sections).toEqual([{ title: 'No due date', data: [c({ id: 'a' })] }])
  })

  it('buckets a past due_at into Overdue', () => {
    const past = new Date(Date.now() - 60_000).toISOString()
    const sections = sectionizeCommitments([c({ id: 'a', due_at: past })])
    expect(sections[0].title).toBe('Overdue')
  })

  it('buckets a future due_at later today into Today', () => {
    const laterToday = new Date(Date.now() + 60_000).toISOString()
    const sections = sectionizeCommitments([c({ id: 'a', due_at: laterToday })])
    expect(sections[0].title).toBe('Today')
  })

  it('omits empty sections and orders Overdue/Today/Upcoming/No due date', () => {
    const past = new Date(Date.now() - 60_000).toISOString()
    const future = new Date(Date.now() + 3 * 86_400_000).toISOString()
    const sections = sectionizeCommitments([
      c({ id: 'a', due_at: past }),
      c({ id: 'b', due_at: future }),
      c({ id: 'c', due_at: null }),
    ])
    expect(sections.map((s) => s.title)).toEqual(['Overdue', 'Upcoming', 'No due date'])
  })
})
