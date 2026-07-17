import { useState, useEffect, useCallback, useRef } from 'react'
import { Toaster, toast } from 'sonner'
import BriefingCard from './components/BriefingCard'
import ChatBar from './components/ChatBar'
import CommitmentList from './components/CommitmentList'
import LoginScreen from './components/LoginScreen'
import PushSetup from './components/PushSetup'
import ReflectionCard from './components/ReflectionCard'
import SettingsPanel from './components/SettingsPanel'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import { useReminders } from './hooks/useReminders'
import { listCommitments } from './api'
import {
  initNotificationActions,
  ensureNotificationPermission,
  syncCommitmentReminders,
} from './lib/notifications'
import { buildProactiveSummary, isProactiveVoiceEnabled } from './lib/proactiveVoice'
import { speak } from './lib/speech'
import './App.css'

/**
 * Root export wraps the app in <AuthProvider> so every component below
 * (and our useAuth hook) sees the same auth state.
 */
export default function App() {
  return (
    <AuthProvider>
      <Gate />
    </AuthProvider>
  )
}

/**
 * Gate decides which top-level view to render based on auth state:
 *
 *   loading  → a quiet placeholder (don't flash LoginScreen briefly)
 *   no user  → <LoginScreen>
 *   user     → <Overwatch>
 *
 * We keep Gate separate from <Overwatch> so the inner app gets fresh
 * mount + state every time someone logs in or out.
 */
function Gate() {
  const { user, loading } = useAuth()

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0f0f0f] flex items-center justify-center">
        <p className="text-zinc-700 text-xs uppercase tracking-widest">Loading…</p>
      </div>
    )
  }

  if (!user) return <LoginScreen />

  return <Overwatch />
}

/**
 * The signed-in experience. Identical to the pre-auth App, with the
 * addition of a tiny user widget in the header.
 *
 * Holds:
 *  - The commitments list state (loaded from the API on mount)
 *  - A `commitmentsVersion` counter that increments on any mutation; the
 *    BriefingCard + StatsBar listen to this and refresh whenever
 *    commitments change.
 *  - `settingsOpen` toggles the settings overlay.
 *
 * useReminders polls the commitments and fires browser notifications when
 * any of them become due.
 *
 * <Toaster> mounts a single notification container. Anywhere in the tree,
 * `toast.success("…")` or `toast.error("…")` will appear here.
 */
function Overwatch() {
  const { user, logout } = useAuth()
  const [commitments, setCommitments] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [commitmentsVersion, setCommitmentsVersion] = useState(0)
  const [settingsOpen, setSettingsOpen] = useState(false)
  // ChatBar is position: fixed, so it doesn't push content. To stop it from
  // overlapping the bottom of the page (especially on phones when the
  // history panel expands), we measure its real height and pad the main
  // container by that amount. ChatBar reports its height via onHeightChange.
  const [chatBarHeight, setChatBarHeight] = useState(96)

  const refresh = useCallback(async () => {
    setError(null)
    try {
      const data = await listCommitments()
      setCommitments(data)
      setCommitmentsVersion((v) => v + 1)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  // Native alarm setup (no-op on web): register the Snooze/Done actions +
  // their handler, and request notification permission, once on mount.
  useEffect(() => {
    initNotificationActions()
    ensureNotificationPermission()
  }, [])

  // Keep the on-device reminder schedule in sync with the commitments. Runs
  // whenever the list changes, so adding/rescheduling/completing a commitment
  // updates the OS-scheduled alarms (no-op on web).
  useEffect(() => {
    syncCommitmentReminders(commitments)
  }, [commitments])

  // Proactive voice: once per app session, after commitments first load, speak
  // a short summary of what's overdue / next — if the user enabled it.
  const spokeProactivelyRef = useRef(false)
  useEffect(() => {
    if (loading || spokeProactivelyRef.current) return
    if (!isProactiveVoiceEnabled()) return
    const summary = buildProactiveSummary(commitments)
    if (summary) {
      spokeProactivelyRef.current = true
      // Small delay so it doesn't talk over the page settling.
      setTimeout(() => speak(summary), 600)
    }
  }, [loading, commitments])

  // After the Google Calendar OAuth flow, the backend redirects back here
  // with ?calendar=<status>. Surface it as a toast, refresh so the calendar
  // picks up the new connection + events, then strip the param from the URL.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const calendarStatus = params.get('calendar')
    if (!calendarStatus) return

    const messages = {
      connected: ['success', 'Google Calendar connected.'],
      denied: ['error', 'Calendar access was declined.'],
      state_mismatch: ['error', 'Calendar connection expired — try again.'],
      exchange_failed: ['error', "Couldn't connect calendar. Try again."],
      missing_code: ['error', "Couldn't connect calendar. Try again."],
    }
    const [kind, text] = messages[calendarStatus] || ['message', 'Calendar updated.']
    toast[kind] ? toast[kind](text) : toast(text)

    if (calendarStatus === 'connected') refresh()

    // Remove the query param so a reload doesn't re-toast.
    params.delete('calendar')
    const clean = window.location.pathname + (params.toString() ? `?${params}` : '')
    window.history.replaceState({}, '', clean)
  }, [refresh])

  useReminders(commitments)

  return (
    <div className="min-h-screen bg-[#0f0f0f] text-[#f5f5f5]">
      {/* Mobile-first width, full stop (ADR-0023) — no desktop-width
          breakpoint. Overwatch's primary target is the native Android app;
          a phone-width single column is the baseline on every screen size,
          not just small ones. paddingBottom is set dynamically from the
          measured ChatBar height (plus a small buffer) so content behind
          the chat is always reachable. */}
      <div
        className="ow-fade-in w-full max-w-md mx-auto px-4 py-8"
        style={{
          // Add the device's top safe-area inset so the header clears the
          // status bar on native (Capacitor) / standalone PWA fullscreen.
          paddingTop: 'calc(2rem + env(safe-area-inset-top))',
          paddingBottom: `${chatBarHeight + 32}px`,
        }}
      >
        <header className="mb-6 flex items-start justify-between">
          <div>
            <h1 className="text-3xl font-bold text-orange-500 mb-1 tracking-tight">
              Overwatch
            </h1>
            <p className="text-zinc-500 text-sm">Things you said you'd do.</p>
          </div>
          <div className="flex items-center gap-2">
            <UserBadge user={user} onLogout={logout} />
            <button
              onClick={() => setSettingsOpen(true)}
              className="text-zinc-600 hover:text-orange-500 transition-colors p-2"
              aria-label="Open settings"
              title="Settings"
            >
              <SettingsIcon />
            </button>
          </div>
        </header>

        {/* Main view: briefing → reflection → commitments → push toggle. The
            chat bar at the bottom is the only way to add or modify
            commitments (ADR-0023 — no structured form, no inline reschedule,
            no groups: chat is the single capture/modify channel). There is
            no calendar grid here on purpose — Overwatch is not a calendar
            (see PRD "What it is NOT"); Google Calendar is read in the
            background as context for the morning briefing only.
            Connect/disconnect lives in Settings. Stats/streaks were built
            and deliberately removed (ADR-0023) — they contradict the "no
            streak tyranny" principle (PRD §5). */}
        <main className="space-y-6">
          <BriefingCard refreshTrigger={commitmentsVersion} />

          {/* Always available alongside the briefing (kept simple for v1 —
              no time-of-day gating). Shows what happened today so far and
              asks about anything still open, rather than reporting on it. */}
          <ReflectionCard refreshTrigger={commitmentsVersion} />

          {loading ? (
            <p className="text-zinc-600 italic text-sm">Loading…</p>
          ) : error ? (
            <div className="flex items-center justify-between gap-3 bg-[#141414] border border-red-900/40 rounded-2xl p-5">
              <p className="text-sm text-zinc-400">
                {error.includes('Failed to fetch')
                  ? "Can't reach Overwatch right now — check your connection."
                  : "Couldn't load your list just now."}
              </p>
              <button
                onClick={refresh}
                className="shrink-0 text-[10px] uppercase tracking-widest text-orange-500 hover:text-orange-400 transition-colors"
              >
                try again
              </button>
            </div>
          ) : (
            <CommitmentList commitments={commitments} onChange={refresh} />
          )}

          <PushSetup />
        </main>
      </div>

      <SettingsPanel open={settingsOpen} onClose={() => setSettingsOpen(false)} />

      {/* ChatBar — fixed at the bottom, talks to /chat. Triggers a refresh
          whenever an add_commitment intent succeeds so the list/calendar/
          briefing pick up the new commitment without a manual reload.
          Reports its current rendered height so the main container can
          pad the bottom enough to avoid being covered. */}
      <ChatBar onAction={refresh} onHeightChange={setChatBarHeight} />

      {/* Toast notifications — themed to match our dark + orange aesthetic. */}
      <Toaster
        position="bottom-right"
        theme="dark"
        toastOptions={{
          style: {
            background: '#141414',
            border: '1px solid #2a2a2a',
            color: '#f5f5f5',
          },
        }}
      />
    </div>
  )
}

/**
 * Small avatar + name display in the top-right of the header. Clicking
 * opens a tiny dropdown with a Sign out button.
 */
function UserBadge({ user, onLogout }) {
  const [open, setOpen] = useState(false)
  const initials = (user.name || user.email || '?')
    .split(' ')
    .map((s) => s[0])
    .slice(0, 2)
    .join('')
    .toUpperCase()

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 px-2 py-1.5 hover:bg-white/[0.04] rounded-lg transition-colors"
        aria-label="Account menu"
      >
        {user.picture ? (
          <img
            src={user.picture}
            alt=""
            className="w-7 h-7 rounded-full border border-white/10"
          />
        ) : (
          <span className="w-7 h-7 rounded-full bg-orange-500/20 border border-orange-500/40 text-orange-300 text-[11px] font-semibold flex items-center justify-center">
            {initials}
          </span>
        )}
      </button>
      {open && (
        <>
          {/* Tap-outside-to-close backdrop — onMouseLeave alone never fires
              on touch, so without this the menu would stay open until the
              avatar is tapped again (mobile-first, ADR-0023). */}
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute right-0 mt-2 w-48 bg-[#141414] border border-white/[0.06] rounded-lg shadow-lg overflow-hidden z-50">
            <div className="px-3 py-2 border-b border-white/[0.06]">
              <p className="text-sm text-zinc-200 truncate">{user.name}</p>
              <p className="text-[11px] text-zinc-500 truncate">{user.email}</p>
            </div>
            <button
              onClick={onLogout}
              className="w-full text-left px-3 py-2 text-sm text-zinc-300 hover:bg-white/[0.04] hover:text-red-400 transition-colors"
            >
              Sign out
            </button>
          </div>
        </>
      )}
    </div>
  )
}

/** Simple gear icon. SVG inline so no extra dependency. */
function SettingsIcon() {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  )
}
