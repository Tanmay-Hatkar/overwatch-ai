/**
 * proactiveVoice.js — Build a short spoken summary of what's pending.
 *
 * Powers the "Overwatch speaks when you open it" feature: on launch, if the
 * user enabled proactive voice, we synthesize a brief, natural sentence about
 * overdue items and the next thing due, then speak it via lib/speech.
 *
 * Pure function (no side effects) so it's easy to test and reuse. The caller
 * decides whether/when to speak it.
 */

const SETTING_KEY = 'overwatch.voice.proactive'

/** Whether proactive voice is enabled (persisted, off by default). */
export function isProactiveVoiceEnabled() {
  try {
    return localStorage.getItem(SETTING_KEY) === '1'
  } catch {
    return false
  }
}

/** Persist the proactive-voice preference. */
export function setProactiveVoiceEnabled(on) {
  try {
    localStorage.setItem(SETTING_KEY, on ? '1' : '0')
  } catch {
    // ignore
  }
}

function fmtTime(iso) {
  return new Date(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
}

/**
 * Build the sentence Overwatch should speak, or null if there's nothing worth
 * saying (so the caller can stay silent).
 *
 * @param {Array} commitments  The user's commitments (CommitmentResponse[]).
 * @returns {string | null}
 */
export function buildProactiveSummary(commitments = []) {
  const now = Date.now()
  const open = commitments.filter((c) => c.status === 'open')

  const overdue = open.filter((c) => c.due_at && new Date(c.due_at).getTime() < now)
  const upcoming = open
    .filter((c) => c.due_at && new Date(c.due_at).getTime() >= now)
    .sort((a, b) => new Date(a.due_at) - new Date(b.due_at))

  if (overdue.length === 0 && upcoming.length === 0) {
    // Nothing scheduled — only speak if there are floating commitments.
    const floating = open.filter((c) => !c.due_at)
    if (floating.length === 0) return null
    return `You have ${floating.length} thing${floating.length > 1 ? 's' : ''} on your list, nothing scheduled yet.`
  }

  const parts = []
  if (overdue.length === 1) {
    parts.push(`One overdue: ${overdue[0].text}.`)
  } else if (overdue.length > 1) {
    parts.push(`${overdue.length} overdue, including ${overdue[0].text}.`)
  }

  if (upcoming.length > 0) {
    const next = upcoming[0]
    parts.push(`Next up: ${next.text} at ${fmtTime(next.due_at)}.`)
  }

  return parts.join(' ')
}

export { SETTING_KEY as PROACTIVE_VOICE_KEY }
