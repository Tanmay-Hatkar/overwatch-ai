import { useState, useEffect, useCallback } from 'react'
import { getTodayBriefing } from '../api'

/**
 * BriefingCard — shows today's LLM-generated morning briefing.
 *
 * Auto-loads on mount. Refresh button regenerates (re-runs the LLM).
 * Shows skeleton during loading, error state if the LLM is unavailable.
 *
 * The `refreshTrigger` prop lets the parent force a refresh — used when
 * commitments change, so the briefing stays in sync without the user
 * clicking refresh.
 */
export default function BriefingCard({ refreshTrigger }) {
  const [briefing, setBriefing] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // `force` bypasses the server-side cache. Used by the refresh button;
  // not used by the auto-load on mount or by the commitment-change trigger
  // (those rely on the backend's cache-freshness check).
  const load = useCallback(async (force = false) => {
    setLoading(true)
    setError(null)
    try {
      const data = await getTodayBriefing(force)
      setBriefing(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load(false)
  }, [load, refreshTrigger])

  return (
    <section className="mb-8 relative">
      {/* Subtle orange glow behind the card to make it the focal point */}
      <div className="absolute inset-0 bg-orange-500/[0.03] rounded-2xl blur-xl pointer-events-none" />

      <div className="relative bg-[#141414] border border-orange-500/20 rounded-2xl p-5">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-[10px] font-semibold tracking-[0.15em] uppercase text-orange-500">
            Today's Briefing
          </h2>
          <button
            onClick={() => load(true)}
            disabled={loading}
            className="text-[10px] uppercase tracking-widest text-zinc-600 hover:text-orange-500 disabled:opacity-50 transition-colors"
            aria-label="Regenerate briefing"
          >
            {loading ? '...' : 'refresh'}
          </button>
        </div>

        {loading && !briefing && <BriefingSkeleton />}

        {error && !loading && (
          <p className="text-red-500 text-sm">
            {error.includes('503')
              ? "Couldn't generate a briefing right now."
              : `Error: ${error}`}
          </p>
        )}

        {briefing && !error && (
          <>
            <p className="text-[15px] leading-relaxed text-zinc-200">
              {briefing.content}
            </p>
            <div className="mt-3 pt-3 border-t border-white/[0.05] flex gap-4 text-[11px] text-zinc-500">
              <span>
                <span className="text-zinc-300">{briefing.today_count}</span> due today
              </span>
              <span>
                <span className={briefing.overdue_count > 0 ? 'text-red-400' : 'text-zinc-300'}>
                  {briefing.overdue_count}
                </span>{' '}
                overdue
              </span>
            </div>
          </>
        )}
      </div>
    </section>
  )
}

/** Three pulsing lines to suggest text is loading. */
function BriefingSkeleton() {
  return (
    <div className="space-y-2 animate-pulse">
      <div className="h-3 bg-[#1e1e1e] rounded w-[90%]" />
      <div className="h-3 bg-[#1e1e1e] rounded w-[75%]" />
      <div className="h-3 bg-[#1e1e1e] rounded w-[60%]" />
    </div>
  )
}
