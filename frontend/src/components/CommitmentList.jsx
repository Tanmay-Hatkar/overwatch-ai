import { updateCommitment, deleteCommitment } from '../api'

/**
 * List of commitments, split into Open (top) and Done (bottom, dimmed).
 *
 * Receives the commitments array and an onChange callback. The callback
 * is invoked after any mutation so the parent can refresh from the API.
 */
export default function CommitmentList({ commitments, onChange }) {
  async function handleToggleDone(commitment) {
    const newStatus = commitment.status === 'done' ? 'open' : 'done'
    await updateCommitment(commitment.id, { status: newStatus })
    onChange()
  }

  async function handleDelete(commitment) {
    await deleteCommitment(commitment.id)
    onChange()
  }

  const open = commitments.filter((c) => c.status === 'open')
  const done = commitments.filter((c) => c.status === 'done')

  return (
    <div>
      <section className="mb-8">
        <h3 className="text-[10px] font-semibold tracking-[0.15em] uppercase text-zinc-600 mb-3">
          Open ({open.length})
        </h3>
        {open.length === 0 ? (
          <p className="text-zinc-600 italic text-sm">
            No open commitments. Add one above.
          </p>
        ) : (
          <ul className="space-y-2">
            {open.map((c) => (
              <li
                key={c.id}
                className="flex items-center gap-3 px-4 py-3 bg-[#1a1a1a] border border-[#2a2a2a] rounded-lg hover:border-[#3a3a3a] transition-colors"
              >
                <input
                  type="checkbox"
                  checked={false}
                  onChange={() => handleToggleDone(c)}
                  className="w-[18px] h-[18px] accent-orange-500 cursor-pointer"
                />
                <span className="flex-1 text-sm">{c.text}</span>
                <button
                  onClick={() => handleDelete(c)}
                  className="text-zinc-600 hover:text-red-500 text-xl px-2 leading-none transition-colors"
                  aria-label="Delete"
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {done.length > 0 && (
        <section>
          <h3 className="text-[10px] font-semibold tracking-[0.15em] uppercase text-zinc-600 mb-3">
            Done ({done.length})
          </h3>
          <ul className="space-y-2">
            {done.map((c) => (
              <li
                key={c.id}
                className="flex items-center gap-3 px-4 py-3 bg-[#1a1a1a] border border-[#2a2a2a] rounded-lg opacity-50"
              >
                <input
                  type="checkbox"
                  checked={true}
                  onChange={() => handleToggleDone(c)}
                  className="w-[18px] h-[18px] accent-orange-500 cursor-pointer"
                />
                <span className="flex-1 text-sm line-through">{c.text}</span>
                <button
                  onClick={() => handleDelete(c)}
                  className="text-zinc-600 hover:text-red-500 text-xl px-2 leading-none transition-colors"
                  aria-label="Delete"
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
