import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { getCalendarConnection, googleCalendarConnectUrl, disconnectCalendar } from '../api'

/**
 * CalendarConnection — Settings-only connect/disconnect control.
 *
 * Google Calendar is background context for the morning briefing, not a
 * visible screen (see ADR-0022 and PRD "What it is NOT" — Overwatch is not
 * a calendar). This replaces the old full-week grid hero on the home page
 * with a single status line + action.
 */
export default function CalendarConnection() {
  const [connected, setConnected] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let cancelled = false
    getCalendarConnection()
      .then((data) => {
        if (!cancelled) setConnected(Boolean(data?.connected))
      })
      .catch(() => {
        if (!cancelled) setConnected(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  async function handleDisconnect() {
    setBusy(true)
    try {
      await disconnectCalendar()
      setConnected(false)
      toast.success('Google Calendar disconnected.')
    } catch (err) {
      toast.error(err.message || "Couldn't disconnect calendar.")
    } finally {
      setBusy(false)
    }
  }

  return (
    <section>
      <h3 className="text-[10px] font-semibold tracking-[0.15em] uppercase text-zinc-600 mb-2">
        Google Calendar
      </h3>
      <p className="text-xs text-zinc-600 mb-3">
        Optional. When connected, your events give the morning briefing more
        context — it's never shown as a calendar view.
      </p>

      {connected === true && (
        <div className="flex items-center justify-between px-4 py-2 rounded-lg bg-emerald-500/[0.08] border border-emerald-500/25">
          <span className="inline-flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wider text-emerald-300">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
            Connected
          </span>
          <button
            onClick={handleDisconnect}
            disabled={busy}
            className="text-[11px] uppercase tracking-wider text-zinc-500 hover:text-red-400 disabled:opacity-50 transition-colors"
          >
            Disconnect
          </button>
        </div>
      )}

      {connected === false && (
        <a
          href={googleCalendarConnectUrl()}
          className="flex items-center justify-center px-4 py-2 rounded-lg bg-[#1a1a1a] border border-[#2a2a2a] hover:border-orange-500/50 text-zinc-200 text-sm transition-colors"
        >
          Connect Google Calendar
        </a>
      )}

      {connected === null && <p className="text-sm text-zinc-600">Checking…</p>}
    </section>
  )
}
