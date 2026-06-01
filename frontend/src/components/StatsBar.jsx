import { useState, useEffect } from 'react'
import { getTodayStats } from '../api'

/**
 * StatsBar — small card showing completion stats + 7-day sparkline.
 *
 * Auto-loads on mount and refreshes whenever `refreshTrigger` changes
 * (parent passes it to invalidate when commitments mutate).
 */
export default function StatsBar({ refreshTrigger }) {
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      setError(null)
      try {
        const data = await getTodayStats()
        if (!cancelled) setStats(data)
      } catch (err) {
        if (!cancelled) setError(err.message)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [refreshTrigger])

  if (loading && !stats) {
    return (
      <section className="mb-6">
        <div className="h-12 bg-[#141414] border border-[#2a2a2a] rounded-xl animate-pulse" />
      </section>
    )
  }

  if (error || !stats) {
    return null // fail silently — stats are nice-to-have, not critical
  }

  return (
    <section className="mb-6">
      <div className="bg-[#141414] border border-[#2a2a2a] rounded-xl p-4 flex items-center gap-6 flex-wrap">
        <Stat label="Today" value={stats.completed_today} accent />
        <Stat label="This week" value={stats.completed_this_week} />
        <Stat
          label="Streak"
          value={stats.streak_days > 0 ? `${stats.streak_days}d` : '—'}
          accent={stats.streak_days >= 3}
        />
        <Sparkline days={stats.daily_completions} />
      </div>
    </section>
  )
}

function Stat({ label, value, accent = false }) {
  return (
    <div className="flex flex-col">
      <span className="text-[9px] font-semibold tracking-[0.15em] uppercase text-zinc-600">
        {label}
      </span>
      <span
        className={`text-xl font-bold tabular-nums ${
          accent ? 'text-orange-500' : 'text-zinc-200'
        }`}
      >
        {value}
      </span>
    </div>
  )
}

/**
 * Sparkline — 7 vertical bars, height proportional to that day's count.
 *
 * Today is the last bar (rightmost), highlighted in orange. Empty days
 * still show a tiny stub so the bar count is visually consistent.
 */
function Sparkline({ days }) {
  if (!days || days.length === 0) return null

  const maxCount = Math.max(1, ...days.map((d) => d.count))

  return (
    <div className="ml-auto flex items-end gap-[3px] h-8" aria-label="Last 7 days">
      {days.map((d, i) => {
        const isToday = i === days.length - 1
        const heightPct = Math.max(8, (d.count / maxCount) * 100)
        return (
          <div
            key={d.date}
            title={`${d.date}: ${d.count} completed`}
            className={`w-[6px] rounded-sm transition-colors ${
              isToday ? 'bg-orange-500' : d.count > 0 ? 'bg-zinc-500' : 'bg-zinc-800'
            }`}
            style={{ height: `${heightPct}%` }}
          />
        )
      })}
    </div>
  )
}
