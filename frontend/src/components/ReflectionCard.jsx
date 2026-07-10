import { useState, useEffect, useCallback } from 'react'
import { getTodayReflection } from '../api'

/**
 * ReflectionCard — shows today's LLM-generated evening reflection.
 *
 * Mirrors BriefingCard's structure and behavior: auto-loads on mount,
 * refresh button regenerates (re-runs the LLM), skeleton during loading,
 * graceful error state.
 *
 * The `refreshTrigger` prop lets the parent force a refresh — used when
 * commitments change, so the reflection stays in sync without the user
 * clicking refresh.
 */
export default function ReflectionCard({ refreshTrigger }) {
  const [reflection, setReflection] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // `force` bypasses the server-side cache. Used by the refresh button;
  // not used by the auto-load on mount or by the commitment-change trigger
  // (those rely on the backend's cache-freshness check).
  const load = useCallback(async (force = false) => {
    setLoading(true)
    setError(null)
    try {
      const data = await getTodayReflection(force)
      setReflection(data)
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
      {/* Subtle indigo glow — distinct from the briefing's orange, so the
          two cards read as related but different moments of the day. */}
      <div className="absolute inset-0 bg-indigo-500/[0.03] rounded-2xl blur-xl pointer-events-none" />

      <div className="relative bg-[#141414] border border-indigo-500/20 rounded-2xl p-5">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-[10px] font-semibold tracking-[0.15em] uppercase text-indigo-400">
            Evening Reflection
          </h2>
          <button
            onClick={() => load(true)}
            disabled={loading}
            className="text-[10px] uppercase tracking-widest text-zinc-600 hover:text-indigo-400 disabled:opacity-50 transition-colors"
            aria-label="Regenerate reflection"
          >
            {loading ? '...' : 'refresh'}
          </button>
        </div>

        {loading && !reflection && <ReflectionSkeleton />}

        {error && !loading && (
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm text-zinc-400">
              {error.includes('Failed to fetch')
                ? "Can't reach Overwatch right now — check your connection."
                : "Couldn't put together your reflection just now."}
            </p>
            <button
              onClick={() => load(true)}
              className="shrink-0 text-[10px] uppercase tracking-widest text-indigo-400 hover:text-indigo-300 transition-colors"
            >
              try again
            </button>
          </div>
        )}

        {reflection && !error && (
          <>
            <p className="text-[15px] leading-relaxed text-zinc-200">
              {reflection.content}
            </p>
            <div className="mt-3 pt-3 border-t border-white/[0.05] flex gap-4 text-[11px] text-zinc-500">
              <span>
                <span className="text-zinc-300">{reflection.done_count}</span> done
              </span>
              <span>
                <span className="text-zinc-300">{reflection.open_count}</span> still open
              </span>
              <span>
                <span className="text-zinc-300">{reflection.abandoned_count}</span> let go
              </span>
            </div>
          </>
        )}
      </div>
    </section>
  )
}

/** Three pulsing lines to suggest text is loading. */
function ReflectionSkeleton() {
  return (
    <div className="space-y-2 animate-pulse">
      <div className="h-3 bg-[#1e1e1e] rounded w-[90%]" />
      <div className="h-3 bg-[#1e1e1e] rounded w-[75%]" />
      <div className="h-3 bg-[#1e1e1e] rounded w-[60%]" />
    </div>
  )
}
