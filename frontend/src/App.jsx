import { useState, useEffect, useCallback } from 'react'
import CommitmentForm from './components/CommitmentForm'
import CommitmentList from './components/CommitmentList'
import { listCommitments } from './api'
import './App.css'

/**
 * Top-level component.
 *
 * Holds the commitments list state. Loads from the API on mount and
 * exposes a refresh() callback that children call after any mutation.
 */
function App() {
  const [commitments, setCommitments] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // useCallback so the reference is stable across renders — important
  // because refresh is passed as a prop to children. Without it, children
  // would re-render every time even when nothing changed.
  const refresh = useCallback(async () => {
    setError(null)
    try {
      const data = await listCommitments()
      setCommitments(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  // Load commitments once when the component mounts.
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
