import { useState, useEffect, useCallback } from 'react'
import BriefingCard from './components/BriefingCard'
import CommitmentForm from './components/CommitmentForm'
import CommitmentList from './components/CommitmentList'
import { listCommitments } from './api'
import './App.css'

/**
 * Top-level component.
 *
 * Holds:
 *  - The commitments list state (loaded from the API on mount)
 *  - A `commitmentsVersion` counter that increments on any mutation; the
 *    BriefingCard listens to this and regenerates the briefing whenever
 *    commitments change.
 */
function App() {
  const [commitments, setCommitments] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [commitmentsVersion, setCommitmentsVersion] = useState(0)

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

  return (
    <div className="min-h-screen bg-[#0f0f0f] text-[#f5f5f5]">
      <div className="max-w-2xl mx-auto px-6 py-12">
        <header className="mb-10">
          <h1 className="text-3xl font-bold text-orange-500 mb-1 tracking-tight">
            Overwatch
          </h1>
          <p className="text-zinc-500 text-sm">Things you said you'd do.</p>
        </header>

        <main>
          <BriefingCard refreshTrigger={commitmentsVersion} />

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
    </div>
  )
}

export default App
