import { useState, useEffect, useCallback } from 'react'
import { Toaster } from 'sonner'
import BriefingCard from './components/BriefingCard'
import ChatBar from './components/ChatBar'
import CommitmentList from './components/CommitmentList'
import LoginScreen from './components/LoginScreen'
import PushSetup from './components/PushSetup'
import SettingsPanel from './components/SettingsPanel'
// CommitmentForm, NotificationStatus, StatsBar, WeeklyCalendar are intentionally
// not rendered right now — see the comment on <main>. Their components still
// live in src/components/ for when we bring them back.
import { AuthProvider, useAuth } from './contexts/AuthContext'
import { useReminders } from './hooks/useReminders'
import { listCommitments } from './api'
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

  useReminders(commitments)

  return (
    <div className="min-h-screen bg-[#0f0f0f] text-[#f5f5f5]">
      {/* Width: full on mobile, 70% of viewport on desktop, capped at 1280px so
          it doesn't sprawl on ultrawide monitors. Bottom padding leaves room
          for the fixed ChatBar so nothing is hidden behind it. */}
      <div className="w-full md:w-[70vw] max-w-[1280px] mx-auto px-6 py-8 pb-40">
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

        {/* Main view simplified to: briefing → commitment list → push toggle.
            The chat bar at the bottom is the primary way to add commitments,
            so the structured form, mock weekly calendar, and floating stats
            bar are hidden. Their components remain imported so we can bring
            them back per-feature later (e.g. real calendar in slice 12). */}
        <main className="space-y-6">
          <BriefingCard refreshTrigger={commitmentsVersion} />

          {loading ? (
            <p className="text-zinc-600 italic text-sm">Loading…</p>
          ) : error ? (
            <p className="text-red-500 text-sm">Error: {error}</p>
          ) : (
            <CommitmentList commitments={commitments} onChange={refresh} />
          )}

          <PushSetup />
        </main>
      </div>

      <SettingsPanel open={settingsOpen} onClose={() => setSettingsOpen(false)} />

      {/* ChatBar — fixed at the bottom, talks to /chat. Triggers a refresh
          whenever an add_commitment intent succeeds so the list/calendar/
          briefing pick up the new commitment without a manual reload. */}
      <ChatBar onAction={refresh} />

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
        <div
          className="absolute right-0 mt-2 w-48 bg-[#141414] border border-white/[0.06] rounded-lg shadow-lg overflow-hidden z-50"
          onMouseLeave={() => setOpen(false)}
        >
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
