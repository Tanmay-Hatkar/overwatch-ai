/**
 * goals.js — pure helpers for weekly rate goals (ADR-0026).
 *
 * All the copy a goal shows lives here so it can be tested in one place
 * and kept honest to PRD §5 principle 3: plain facts and days left, never
 * "behind", "failed", or a score. The server decides the week state
 * (backend/app/services/goal_service.py); this only words it.
 */

function plural(n, one, many) {
  return `${n} ${n === 1 ? one : many}`
}

/** Fraction 0..1 for the progress bar (capped, safe for a 0 target). */
export function goalFraction(goal) {
  if (!goal.target_count) return 0
  return Math.min(1, goal.done_this_week / goal.target_count)
}

/** The one-line status under a goal's title. */
export function goalStatusLine(goal) {
  switch (goal.state) {
    case 'met':
      return goal.done_this_week > goal.target_count
        ? `Target reached, plus ${goal.done_this_week - goal.target_count} extra`
        : 'Target reached for this week'
    case 'settled':
      return 'You called this week good. Fresh start Monday.'
    default: {
      const left = goal.days_left === 1 ? 'last day of the week' : `${plural(goal.days_left, 'day', 'days')} left`
      return `${goal.remaining} to go · ${left}`
    }
  }
}

/**
 * The end-of-week check-in question, or null when there's nothing to ask.
 * Asked once: the server stops returning 'check_in' after any answer.
 */
export function goalCheckInPrompt(goal) {
  if (goal.state !== 'check_in') return null
  // The numbers are already in the status line right above; this only asks.
  const when = goal.days_left === 1 ? 'Last day of the week.' : "The week's nearly done."
  return `${when} Keep going, adjust the target, or call this week good?`
}

/** Header summary for the goals section, e.g. "Week of Oct 12". */
export function weekLabel(goals) {
  if (!goals.length) return ''
  const [y, m, d] = goals[0].week_start.split('-').map(Number)
  const monday = new Date(y, m - 1, d)
  return `Week of ${monday.toLocaleDateString([], { month: 'short', day: 'numeric' })}`
}

/**
 * Apply a +amount optimistically, mirroring the server's state rules so
 * the card doesn't flicker while the request is in flight.
 */
export function withOptimisticLog(goal, amount = 1) {
  const done = goal.done_this_week + amount
  const met = done >= goal.target_count
  return {
    ...goal,
    done_this_week: done,
    remaining: Math.max(0, goal.target_count - done),
    state: met ? 'met' : goal.state,
  }
}
