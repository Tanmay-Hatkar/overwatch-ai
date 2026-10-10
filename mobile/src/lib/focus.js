/**
 * focus.js — pure helpers behind the home screen's "Up next" card.
 *
 * The card answers one question: "what should I start right now?" (the
 * "helps you start" half of the product promise). It prefers the soonest
 * commitment still ahead of you today-ish; failing that, the most recent
 * one that slipped by, framed as "still on?" rather than "overdue"
 * (PRD §5 principle 3: recall, never judgment).
 */

// How far ahead an upcoming commitment can be and still be "up next".
// Beyond this, the card would be nagging about tomorrow at 9pm tonight.
export const UP_NEXT_WINDOW_HOURS = 12

/**
 * Pick the commitment the home screen should focus on.
 *
 * @param {Array} commitments - any commitments; only open + timed ones count
 * @param {Date} now
 * @returns {{ commitment: object, kind: 'upcoming' | 'earlier' } | null}
 */
export function pickUpNext(commitments, now = new Date()) {
  const timed = commitments
    .filter((c) => c.status === 'open' && c.due_at)
    .map((c) => ({ c, due: new Date(c.due_at) }))

  const windowEnd = now.getTime() + UP_NEXT_WINDOW_HOURS * 3600 * 1000
  const upcoming = timed
    .filter(({ due }) => due >= now && due.getTime() <= windowEnd)
    .sort((a, b) => a.due - b.due)
  if (upcoming.length > 0) return { commitment: upcoming[0].c, kind: 'upcoming' }

  const earlier = timed.filter(({ due }) => due < now).sort((a, b) => b.due - a.due)
  if (earlier.length > 0) return { commitment: earlier[0].c, kind: 'earlier' }

  return null
}

/**
 * Human relative time: "in 48 min", "in 2 hr", "in 1 hr 30 min",
 * "20 min ago", "3 hr ago", "now".
 *
 * @param {Date} due
 * @param {Date} now
 * @returns {string}
 */
export function relativeTime(due, now = new Date()) {
  const diffMin = Math.round((due.getTime() - now.getTime()) / 60000)
  const abs = Math.abs(diffMin)
  if (abs < 1) return 'now'
  const hours = Math.floor(abs / 60)
  const mins = abs % 60
  let span
  if (hours === 0) span = `${mins} min`
  else if (mins === 0 || hours >= 3) span = `${hours} hr`
  else span = `${hours} hr ${mins} min`
  return diffMin > 0 ? `in ${span}` : `${span} ago`
}

/**
 * Time-of-day greeting for the header.
 *
 * @param {Date} now
 * @returns {string}
 */
export function greetingFor(now = new Date()) {
  const h = now.getHours()
  if (h < 5) return 'Still up'
  if (h < 12) return 'Good morning'
  if (h < 17) return 'Good afternoon'
  return 'Good evening'
}

/**
 * First name for the greeting, from the user's display name (falling back
 * to the email's local part). Returns '' when there's nothing usable.
 *
 * @param {{ name?: string, email?: string } | null} user
 * @returns {string}
 */
export function firstNameOf(user) {
  const source = (user?.name || user?.email?.split('@')[0] || '').trim()
  return source.split(/\s+/)[0] || ''
}
