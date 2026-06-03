import { useState, useEffect, useCallback } from 'react'
import { Toaster } from 'sonner'
import BriefingCard from './components/BriefingCard'
import ChatBar from './components/ChatBar'
import CommitmentForm from './components/CommitmentForm'
import CommitmentList from './components/CommitmentList'
import NotificationStatus from './components/NotificationStatus'
import PushSetup from './components/PushSetup'
import SettingsPanel from './components/SettingsPanel'
import StatsBar from './components/StatsBar'
import WeeklyCalendar from './components/WeeklyCalendar'
import { useReminders } from './hooks/useReminders'
import { listCommitments } from './api'
import './App.css'

/**
 * Top-level component.
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
function App() {
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
      {/* Bottom padding leaves room for the fixed ChatBar so nothing is hidden */}
      <div className="max-w-2xl mx-auto px-6 py-12 pb-40">
        <header className="mb-10 flex items-start justify-between">
          <div>
            <h1 className="text-3xl font-bold text-orange-500 mb-1 tracking-tight">
              Overwatch
            </h1>
            <p className="text-zinc-500 text-sm">Things you said you'd do.</p>
          </div>
          <button
            onClick={() => setSettingsOpen(true)}
            className="text-zinc-600 hover:text-orange-500 transition-colors p-2"
            aria-label="Open settings"
            title="Settings"
          >
            <SettingsIcon />
          </button>
        </header>

        <main>
          <BriefingCard refreshTrigger={commitmentsVersion} />

          <WeeklyCalendar
            commitments={commitments}
            refreshTrigger={commitmentsVersion}
          />

          <StatsBar refreshTrigger={commitmentsVersion} />

          <NotificationStatus />
          <PushSetup />
          <CommitmentForm onCreated={refresh} />

          {loading ? (
            <p className="text-zinc-600 italic text-sm">Loading…</p>
          ) : error ? (
            <p className="text-red-500 text-sm">Error: {error}</p>
          ) : (
            <CommitmentList commitments={commitments} onChange={refresh} />
          )}
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

export default App
