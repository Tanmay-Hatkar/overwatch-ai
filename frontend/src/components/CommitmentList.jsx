import { updateCommitment, deleteCommitment } from '../api'

/**
 * List of commitments, split into Open (top) and Done (bottom, dimmed).
 *
 * Receives the commitments array and an onChange callback. The callback
 * is invoked after any mutation so the parent can refresh from the API.
 *
 * When a commitment has a due_at, we display it as a relative-ish label
 * (e.g., "due Thu 3pm", "overdue", "due today"). Overdue + open
 * commitments get a red accent to draw attention.
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
              <CommitmentItem
                key={c.id}
                commitment={c}
                onToggle={() => handleToggleDone(c)}
                onDelete={() => handleDelete(c)}
              />
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
              <CommitmentItem
                key={c.id}
                commitment={c}
                onToggle={() => handleToggleDone(c)}
                onDelete={() => handleDelete(c)}
              />
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}

/**
 * Single row for one commitment. Extracted so we don't repeat markup
 * between Open and Done sections.
 */
function CommitmentItem({ commitment, onToggle, onDelete }) {
  const isDone = commitment.status === 'done'
  const dueInfo = formatDueAt(commitment.due_at, isDone)

  return (
    <li
      className={`flex items-center gap-3 px-4 py-3 bg-[#1a1a1a] border rounded-lg transition-colors ${
        isDone
          ? 'border-[#2a2a2a] opacity-50'
          : dueInfo?.overdue
            ? 'border-red-900/60 hover:border-red-700'
            : 'border-[#2a2a2a] hover:border-[#3a3a3a]'
      }`}
    >
      <input
        type="checkbox"
        checked={isDone}
        onChange={onToggle}
        className="w-[18px] h-[18px] accent-orange-500 cursor-pointer"
      />
      <div className="flex-1 min-w-0">
        <p className={`text-sm ${isDone ? 'line-through' : ''}`}>
          {commitment.text}
        </p>
        {dueInfo && (
          <p
            className={`text-[11px] mt-0.5 ${
              dueInfo.overdue && !isDone ? 'text-red-400' : 'text-zinc-500'
            }`}
          >
            {dueInfo.label}
          </p>
        )}
      </div>
      <button
        onClick={onDelete}
        className="text-zinc-600 hover:text-red-500 text-xl px-2 leading-none transition-colors"
        aria-label="Delete"
      >
        ×
      </button>
    </li>
  )
}

/**
 * Format a due_at ISO string for display next to a commitment.
 *
 * Returns:
 *   - null if no due_at
 *   - { label, overdue } where label is a short human string and
 *     overdue is true if the due date has passed (used for styling)
 */
function formatDueAt(dueAt, isDone) {
  if (!dueAt) return null

  const due = new Date(dueAt)
  const now = new Date()
  const overdue = !isDone && due < now

  // Same calendar day?
  const sameDay =
    due.getFullYear() === now.getFullYear() &&
    due.getMonth() === now.getMonth() &&
    due.getDate() === now.getDate()

  const time = due.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })

  let label
  if (overdue) {
    label = `overdue · ${time}`
  } else if (sameDay) {
    label = `due today · ${time}`
  } else {
    const day = due.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' })
    label = `due ${day} · ${time}`
  }

  return { label, overdue }
}
