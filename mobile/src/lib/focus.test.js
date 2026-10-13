import { firstNameOf, greetingFor, pickUpNext, relativeTime, UP_NEXT_WINDOW_HOURS } from './focus'

const NOW = new Date('2026-10-09T20:00:00')
const at = (h, m = 0, dayOffset = 0) => {
  const d = new Date(NOW)
  d.setDate(d.getDate() + dayOffset)
  d.setHours(h, m, 0, 0)
  return d.toISOString()
}
const open = (id, due_at) => ({ id, status: 'open', due_at })

describe('pickUpNext', () => {
  it('picks the soonest upcoming open commitment', () => {
    const result = pickUpNext([open('b', at(23)), open('a', at(21)), open('c', null)], NOW)
    expect(result).toEqual({ commitment: expect.objectContaining({ id: 'a' }), kind: 'upcoming' })
  })

  it('ignores done commitments and ones without a time', () => {
    const done = { id: 'd', status: 'done', due_at: at(21) }
    expect(pickUpNext([done, open('x', null)], NOW)).toBeNull()
  })

  it('ignores upcoming commitments beyond the window', () => {
    const farAhead = open('far', new Date(NOW.getTime() + (UP_NEXT_WINDOW_HOURS + 1) * 3600e3).toISOString())
    expect(pickUpNext([farAhead], NOW)).toBeNull()
  })

  it('falls back to the most recent one that slipped by, as "earlier"', () => {
    const result = pickUpNext([open('old', at(9)), open('recent', at(18))], NOW)
    expect(result).toEqual({ commitment: expect.objectContaining({ id: 'recent' }), kind: 'earlier' })
  })

  it('prefers anything upcoming over something that slipped', () => {
    const result = pickUpNext([open('slipped', at(18)), open('soon', at(22))], NOW)
    expect(result.kind).toBe('upcoming')
    expect(result.commitment.id).toBe('soon')
  })
})

describe('relativeTime', () => {
  const plus = (min) => new Date(NOW.getTime() + min * 60000)
  it.each([
    [0, 'now'],
    [48, 'in 48 min'],
    [120, 'in 2 hr'],
    [90, 'in 1 hr 30 min'],
    [200, 'in 3 hr'],
    [-20, '20 min ago'],
    [-180, '3 hr ago'],
  ])('%i minutes → %s', (min, expected) => {
    expect(relativeTime(plus(min), NOW)).toBe(expected)
  })
})

describe('greetingFor', () => {
  const atHour = (h) => new Date(2026, 9, 9, h)
  it.each([
    [2, 'Still up'],
    [8, 'Good morning'],
    [13, 'Good afternoon'],
    [20, 'Good evening'],
  ])('%i:00 → %s', (h, expected) => {
    expect(greetingFor(atHour(h))).toBe(expected)
  })
})

describe('firstNameOf', () => {
  it('uses the first word of the display name', () => {
    expect(firstNameOf({ name: 'Tanmay Hatkar', email: 't@example.com' })).toBe('Tanmay')
  })
  it('falls back to the email local part', () => {
    expect(firstNameOf({ email: 'demo@example.com' })).toBe('demo')
  })
  it('returns empty string with no user', () => {
    expect(firstNameOf(null)).toBe('')
  })
})
