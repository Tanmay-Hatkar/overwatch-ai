import { useEffect, useState } from 'react'
import { getWeekEvents } from '../api'

/**
 * WeeklyCalendar — full-width hero showing the current Mon-Sun week.
 *
 * Renders a time-grid (8am-7pm) with seven day columns. Each column shows:
 *   - Calendar events as positioned blocks (from /calendar/week)
 *   - Commitments-with-due-times as small markers at their due time
 *
 * The component takes `commitments` as a prop so it can render them
 * alongside events without a second fetch. Events are pulled on mount and
 * whenever `refreshTrigger` changes (so the briefing's auto-refresh signal
 * also keeps this in sync).
 *
 * Today's column gets a subtle orange tint. Live "now" events get an
 * orange glow. Past events are dimmed.
 */

const HOUR_HEIGHT = 44
const START_HOUR = 8
const END_HOUR = 19
const TOTAL_HOURS = END_HOUR - START_HOUR
const TOTAL_HEIGHT = TOTAL_HOURS * HOUR_HEIGHT
const HOURS = Array.from({ length: TOTAL_HOURS }, (_, i) => START_HOUR + i)

function formatHour(h) {
  if (h === 12) return '12p'
  return h < 12 ? `${h}a` : `${h - 12}p`
}

function formatTime(iso) {
  if (!iso || !iso.includes('T')) return 'All day'
  return new Date(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
}

function isNow(start, end) {
  if (!start || !end) return false
  const now = Date.now()
  return new Date(start).getTime() <= now && now <= new Date(end).getTime()
}

function isPast(end) {
  if (!end) return false
  return new Date(end).getTime() < Date.now()
}

/** Convert an ISO datetime to its local date string (YYYY-MM-DD). */
function localDateOf(iso) {
  return new Date(iso).toLocaleDateString('en-CA')
}

/** Build a {top, height} CSS style for an event spanning start..end. */
function getEventStyle(start, end) {
  const s = new Date(start)
  const e = new Date(end)
  const startHr = s.getHours() + s.getMinutes() / 60
  const endHr = e.getHours() + e.getMinutes() / 60
  const clampedStart = Math.max(START_HOUR, Math.min(END_HOUR, startHr))
  const clampedEnd = Math.max(START_HOUR, Math.min(END_HOUR, endHr))
  return {
    top: `${(clampedStart - START_HOUR) * HOUR_HEIGHT}px`,
    height: `${Math.max(22, (clampedEnd - clampedStart) * HOUR_HEIGHT)}px`,
  }
}

/** Build a {top} CSS style for a point-in-time marker (commitment due_at). */
function getMarkerStyle(due_at) {
  const d = new Date(due_at)
  const hr = d.getHours() + d.getMinutes() / 60
  const clamped = Math.max(START_HOUR, Math.min(END_HOUR, hr))
  return { top: `${(clamped - START_HOUR) * HOUR_HEIGHT}px` }
}

export default function WeeklyCalendar({ commitments = [], refreshTrigger }) {
  const [events, setEvents] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    getWeekEvents()
      .then((data) => {
        if (!cancelled) setEvents(data || [])
      })
      .catch(() => {
        if (!cancelled) setEvents([])
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [refreshTrigger])

  const todayStr = new Date().toLocaleDateString('en-CA')

  // Build Mon-Sun for the current week.
  const weekDays = Array.from({ length: 7 }, (_, i) => {
    const d = new Date()
    // Adjust to Monday of this week: getDay() is 0 (Sun) - 6 (Sat).
    // We want Monday = 1; so back up by (getDay()+6)%7 days.
    const offsetToMonday = (d.getDay() + 6) % 7
    d.setDate(d.getDate() - offsetToMonday + i)
    return {
      dateStr: d.toLocaleDateString('en-CA'),
      dayName: d.toLocaleDateString('en-US', { weekday: 'short' }),
      dayNum: d.getDate(),
    }
  })

  // Bucket events by local date.
  const eventsByDate = {}
  weekDays.forEach((d) => {
    eventsByDate[d.dateStr] = []
  })
  events.forEach((ev) => {
    if (!ev.start_at) return
    const key = localDateOf(ev.start_at)
    if (eventsByDate[key] !== undefined) eventsByDate[key].push(ev)
  })

  // Bucket commitments-with-due-times by local date.
  const commitmentsByDate = {}
  weekDays.forEach((d) => {
    commitmentsByDate[d.dateStr] = []
  })
  commitments.forEach((c) => {
    if (!c.due_at) return
    const key = localDateOf(c.due_at)
    if (commitmentsByDate[key] !== undefined) commitmentsByDate[key].push(c)
  })

  return (
    <section className="mb-8">
      <div className="bg-[#141414] border border-white/[0.05] rounded-2xl p-5">
        {/* Section label */}
        <div className="flex items-center gap-3 mb-4">
          <span className="text-[10px] font-semibold tracking-[0.15em] uppercase text-zinc-600">
            This Week
          </span>
          <div className="flex-1 h-px bg-white/[0.04]" />
        </div>

        {loading ? (
          <CalendarSkeleton />
        ) : (
          <div className="overflow-x-auto">
            <div className="min-w-[560px]">
              {/* Day headers */}
              <div className="flex mb-1">
                <div className="shrink-0" style={{ width: '32px' }} />
                <div className="flex-1 grid grid-cols-7 gap-px">
                  {weekDays.map((day) => {
                    const isToday = day.dateStr === todayStr
                    return (
                      <div key={day.dateStr} className="text-center pb-2">
                        <p
                          className={`text-[10px] font-semibold uppercase tracking-wider ${
                            isToday ? 'text-orange-500' : 'text-zinc-600'
                          }`}
                        >
                          {day.dayName}
                        </p>
                        <div
                          className={`w-6 h-6 rounded-full mx-auto flex items-center justify-center mt-0.5 ${
                            isToday ? 'bg-orange-500' : ''
                          }`}
                        >
                          <span
                            className={`text-xs font-bold tabular-nums ${
                              isToday ? 'text-black' : 'text-zinc-500'
                            }`}
                          >
                            {day.dayNum}
                          </span>
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>

              {/* Time grid */}
              <div className="flex">
                {/* Time labels */}
                <div className="shrink-0 flex flex-col" style={{ width: '32px' }}>
                  {HOURS.map((h) => (
                    <div
                      key={h}
                      className="flex items-start justify-end pr-1.5"
                      style={{ height: `${HOUR_HEIGHT}px` }}
                    >
                      <span className="text-[9px] font-mono text-zinc-700 -translate-y-px">
                        {formatHour(h)}
                      </span>
                    </div>
                  ))}
                </div>

                {/* Day columns */}
                <div className="flex-1 grid grid-cols-7 gap-px">
                  {weekDays.map((day) => {
                    const isToday = day.dateStr === todayStr
                    const dayEvents = eventsByDate[day.dateStr] || []
                    const dayCommitments = commitmentsByDate[day.dateStr] || []

                    return (
                      <div
                        key={day.dateStr}
                        className={`relative rounded-lg ${
                          isToday ? 'bg-orange-500/[0.04]' : ''
                        }`}
                        style={{ height: `${TOTAL_HEIGHT}px` }}
                      >
                        {/* Hour grid lines */}
                        {HOURS.map((_, i) => (
                          <div
                            key={i}
                            className="absolute left-0 right-0 border-t border-white/[0.04]"
                            style={{ top: `${i * HOUR_HEIGHT}px` }}
                          />
                        ))}

                        {/* Event blocks */}
                        {dayEvents.map((event) => (
                          <EventBlock
                            key={event.id}
                            event={event}
                            isToday={isToday}
                          />
                        ))}

                        {/* Commitment markers */}
                        {dayCommitments.map((c) => (
                          <CommitmentMarker key={c.id} commitment={c} />
                        ))}
                      </div>
                    )
                  })}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </section>
  )
}

function EventBlock({ event, isToday }) {
  const now = isNow(event.start_at, event.end_at)
  const past = isPast(event.end_at)

  const stateClass = past
    ? 'bg-[#1a1a1a] border border-white/[0.05] text-zinc-600 opacity-40'
    : now
      ? 'bg-orange-500/[0.15] border border-orange-500/50 text-orange-200 shadow-[0_0_8px_rgba(249,115,22,0.2)]'
      : isToday
        ? 'bg-orange-500/[0.08] border border-orange-500/20 text-orange-200/80'
        : 'bg-[#1e1e1e] border border-white/[0.08] text-zinc-400 hover:bg-[#242424]'

  return (
    <div
      title={[
        event.title,
        `${formatTime(event.start_at)} – ${formatTime(event.end_at)}`,
        event.location,
      ]
        .filter(Boolean)
        .join('\n')}
      className={`absolute left-0.5 right-0.5 rounded-md px-1.5 py-1 overflow-hidden cursor-default select-none transition-colors ${stateClass}`}
      style={getEventStyle(event.start_at, event.end_at)}
    >
      <p className="text-[10px] font-medium leading-tight truncate">{event.title}</p>
      <p className="text-[9px] opacity-60 leading-tight">{formatTime(event.start_at)}</p>
    </div>
  )
}

function CommitmentMarker({ commitment }) {
  const isDone = commitment.status === 'done'
  const past = isPast(commitment.due_at)
  const overdue = !isDone && past

  // Visible block (not a 4px line) so users can see at a glance that their
  // commitment landed on the calendar. Colored by state:
  //   - done     → muted zinc
  //   - overdue  → red
  //   - open     → orange (matches the rest of the brand)
  const stateClass = isDone
    ? 'bg-zinc-800/60 border border-zinc-700 text-zinc-500 line-through'
    : overdue
      ? 'bg-red-500/15 border border-red-500/50 text-red-200'
      : 'bg-orange-500/15 border border-orange-500/40 text-orange-200 hover:bg-orange-500/25'

  return (
    <div
      title={`${commitment.text}\n${formatTime(commitment.due_at)}`}
      className={`absolute left-0.5 right-0.5 rounded-md px-1.5 py-1 overflow-hidden cursor-default select-none transition-colors ${stateClass}`}
      style={{
        ...getMarkerStyle(commitment.due_at),
        // 30-min wide visual block so it's actually visible. Adjust height
        // to match an event block's minimum so commitments sit alongside
        // events without being lost in the grid.
        height: '28px',
      }}
    >
      <p className="text-[10px] font-medium leading-tight truncate">
        {commitment.text}
      </p>
      <p className="text-[9px] opacity-60 leading-tight">
        {formatTime(commitment.due_at)}
      </p>
    </div>
  )
}

function CalendarSkeleton() {
  return (
    <div className="flex gap-1.5">
      {Array.from({ length: 7 }, (_, i) => (
        <div key={i} className="flex-1 space-y-1.5">
          <div
            className="h-8 rounded-lg bg-[#1e1e1e] animate-pulse"
            style={{ opacity: Math.max(0.15, 1 - i * 0.1) }}
          />
          <div
            className="h-5 rounded-md bg-[#1a1a1a] animate-pulse"
            style={{ opacity: Math.max(0.1, 0.6 - i * 0.07) }}
          />
        </div>
      ))}
    </div>
  )
}
