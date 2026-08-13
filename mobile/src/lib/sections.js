/**
 * sections.js — groups open commitments into Overdue / Today / Upcoming /
 * No due date sections for a SectionList.
 *
 * The web app (frontend/src/components/CommitmentList.jsx) only offers an
 * All/Due Today/Overdue *filter* toggle, not real grouping — ADR-0023
 * explicitly cut *manual* group-assignment ("list-management ceremony").
 * This is different: sections are entirely derived from due_at, nothing for
 * the user to assign or maintain, so it doesn't reintroduce that ceremony.
 *
 * Date comparisons reuse plain Date/local-time semantics, same as the web
 * app — no timezone param needed here (unlike briefings/reflections) since
 * this is pure client-side comparison against the device's own clock.
 */

const SECTION_ORDER = ['Overdue', 'Today', 'Upcoming', 'No due date']

function isSameDay(a, b) {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  )
}

/**
 * @param {Array} commitments - open commitments (status === 'open')
 * @returns {Array<{ title: string, data: Array }>} SectionList-ready sections,
 *   omitting any section with zero items. "Upcoming" and "Today" are sorted
 *   soonest-first; "Overdue" is sorted most-overdue-first (oldest due date
 *   first, i.e. the one that's been waiting longest surfaces at the top).
 */
export function sectionizeCommitments(commitments) {
  const now = new Date()
  const buckets = { Overdue: [], Today: [], Upcoming: [], 'No due date': [] }

  for (const c of commitments) {
    if (!c.due_at) {
      buckets['No due date'].push(c)
      continue
    }
    const due = new Date(c.due_at)
    if (due < now) {
      buckets.Overdue.push(c)
    } else if (isSameDay(due, now)) {
      buckets.Today.push(c)
    } else {
      buckets.Upcoming.push(c)
    }
  }

  buckets.Overdue.sort((a, b) => new Date(a.due_at) - new Date(b.due_at))
  buckets.Today.sort((a, b) => new Date(a.due_at) - new Date(b.due_at))
  buckets.Upcoming.sort((a, b) => new Date(a.due_at) - new Date(b.due_at))
  // "No due date" keeps API order (newest-first, matching backend default).

  return SECTION_ORDER.map((title) => ({ title, data: buckets[title] })).filter(
    (section) => section.data.length > 0,
  )
}
