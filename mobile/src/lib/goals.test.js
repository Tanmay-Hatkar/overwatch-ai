import { goalCheckInPrompt, goalFraction, goalStatusLine, weekLabel, withOptimisticLog } from './goals'

const base = {
  id: 'g1',
  text: 'Job applications',
  target_count: 10,
  done_this_week: 3,
  remaining: 7,
  days_left: 4,
  state: 'in_progress',
  week_start: '2026-10-12',
}

describe('goalFraction', () => {
  it('is done/target, capped at 1', () => {
    expect(goalFraction(base)).toBeCloseTo(0.3)
    expect(goalFraction({ ...base, done_this_week: 14 })).toBe(1)
    expect(goalFraction({ ...base, target_count: 0 })).toBe(0)
  })
})

describe('goalStatusLine', () => {
  it('states what is left and days left, no judgment', () => {
    expect(goalStatusLine(base)).toBe('7 to go · 4 days left')
  })

  it('names the last day plainly', () => {
    expect(goalStatusLine({ ...base, days_left: 1 })).toBe('7 to go · last day of the week')
  })

  it('reads the same in the check-in state', () => {
    expect(goalStatusLine({ ...base, state: 'check_in', days_left: 2 })).toBe('7 to go · 2 days left')
  })

  it('acknowledges a met target, and extras', () => {
    expect(goalStatusLine({ ...base, state: 'met', done_this_week: 10, remaining: 0 })).toBe(
      'Target reached for this week',
    )
    expect(goalStatusLine({ ...base, state: 'met', done_this_week: 12, remaining: 0 })).toBe(
      'Target reached, plus 2 extra',
    )
  })

  it('frames a settled week as a choice', () => {
    expect(goalStatusLine({ ...base, state: 'settled' })).toMatch(/called this week good/)
  })

  it('never uses judgment words', () => {
    const states = ['in_progress', 'check_in', 'met', 'settled']
    for (const state of states) {
      const line = `${goalStatusLine({ ...base, state })} ${goalCheckInPrompt({ ...base, state }) || ''}`
      expect(line).not.toMatch(/behind|fail|only|missed|overdue/i)
    }
  })
})

describe('goalCheckInPrompt', () => {
  it('is null unless the server says check_in', () => {
    expect(goalCheckInPrompt(base)).toBeNull()
    expect(goalCheckInPrompt({ ...base, state: 'met' })).toBeNull()
  })

  it('asks the renegotiation question without repeating the numbers', () => {
    expect(goalCheckInPrompt({ ...base, state: 'check_in', days_left: 2 })).toBe(
      "The week's nearly done. Keep going, adjust the target, or call this week good?",
    )
    expect(goalCheckInPrompt({ ...base, state: 'check_in', days_left: 1 })).toMatch(/^Last day of the week\./)
  })
})

describe('weekLabel', () => {
  it('labels the week by its Monday', () => {
    expect(weekLabel([base])).toMatch(/^Week of Oct 12$/)
    expect(weekLabel([])).toBe('')
  })
})

describe('withOptimisticLog', () => {
  it('adds progress and flips to met at the target', () => {
    const one = withOptimisticLog(base)
    expect(one.done_this_week).toBe(4)
    expect(one.remaining).toBe(6)
    expect(one.state).toBe('in_progress')

    const done = withOptimisticLog({ ...base, done_this_week: 9, remaining: 1, state: 'check_in' })
    expect(done.state).toBe('met')
    expect(done.remaining).toBe(0)
  })
})
