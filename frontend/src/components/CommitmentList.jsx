import { useState } from 'react'
import { toast } from 'sonner'
import { updateCommitment, deleteCommitment } from '../api'

/**
 * List of commitments, split into Open (top) and Done (bottom, dimmed).
 *
 * Features:
 *   - Filter toggle (All / Due Today / Overdue) for the Open section
 *   - Inline edit on click
 *   - Visual marker for overdue commitments (red border + red due label)
 *
 * Receives the commitments array and an onChange callback. The callback
 * is invoked after any mutation so the parent can refresh from the API.
 */
export default function CommitmentList({ commitments, onChange }) {
  const [filter, setFilter] = useState('all')

  async function handleToggleDone(commitment) {
    const newStatus = commitment.status === 'done' ? 'open' : 'done'
    try {
      await updateCommitment(commitment.id, { status: newStatus })
      if (newStatus === 'done') {
        toast.success(`Done: ${commitment.text}`)
      }
      onChange()
    } catch (err) {
      toast.error(err.message || "Couldn't update commitment.")
    }
  }

  async function handleDelete(commitment) {
    try {
      await deleteCommitment(commitment.id)
      toast.success(`Deleted: ${commitment.text}`)
      onChange()
    } catch (err) {
      toast.error(err.message || "Couldn't delete commitment.")
    }
  }

  async function handleEdit(commitment, newText) {
    try {
      await updateCommitment(commitment.id, { text: newText })
      onChange()
    } catch (err) {
      toast.error(err.message || "Couldn't save edit.")
    }
  }

  async function handleReschedule(commitment, isoDueAt) {
    // isoDueAt is a full UTC ISO string (or already-converted). Sending it
    // reschedules the commitment; the backend stores UTC, the UI renders local.
    try {
      await updateCommitment(commitment.id, { due_at: isoDueAt })
      toast.success(`Rescheduled: ${commitment.text}`)
      onChange()
    } catch (err) {
      toast.error(err.message || "Couldn't reschedule.")
    }
  }

  const open = commitments.filter((c) => c.status === 'open')
  const done = commitments.filter((c) => c.status === 'done')

  // Helpers for filtering by due_at relative to "now"
  const now = new Date()

  const isDueToday = (c) => {
    if (!c.due_at) return false
    const due = new Date(c.due_at)
    return (
      due.getFullYear() === now.getFullYear() &&
      due.getMonth() === now.getMonth() &&
      due.getDate() === now.getDate()
    )
  }

  const isOverdue = (c) => {
    if (!c.due_at) return false
    return new Date(c.due_at) < now
  }

  const counts = {
    all: open.length,
    due_today: open.filter(isDueToday).length,
    overdue: open.filter(isOverdue).length,
  }

  let visibleOpen = open
  if (filter === 'due_today') visibleOpen = open.filter(isDueToday)
  else if (filter === 'overdue') visibleOpen = open.filter(isOverdue)

  const emptyMessage =
    filter === 'all'
      ? "Nothing yet. Tell Overwatch what you said you'd do ↓"
      : filter === 'due_today'
        ? 'Nothing due today.'
        : 'Nothing overdue.'

  return (
    <div>
      <section className="mb-8">
        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <h3 className="text-[10px] font-semibold tracking-[0.15em] uppercase text-zinc-600">
            Open
          </h3>
          <div className="flex gap-1">
            <FilterButton active={filter === 'all'} onClick={() => setFilter('all')} count={counts.all}>
              All
            </FilterButton>
            <FilterButton active={filter === 'due_today'} onClick={() => setFilter('due_today')} count={counts.due_today}>
              Due Today
            </FilterButton>
            <FilterButton active={filter === 'overdue'} onClick={() => setFilter('overdue')} count={counts.overdue}>
              Overdue
            </FilterButton>
          </div>
        </div>

        {visibleOpen.length === 0 ? (
          <p className="text-zinc-600 italic text-sm">{emptyMessage}</p>
        ) : (
          <ul className="space-y-2">
            {visibleOpen.map((c) => (
              <CommitmentItem
                key={c.id}
                commitment={c}
                onToggle={() => handleToggleDone(c)}
                onDelete={() => handleDelete(c)}
                onEdit={(newText) => handleEdit(c, newText)}
                onReschedule={(iso) => handleReschedule(c, iso)}
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
                onEdit={(newText) => handleEdit(c, newText)}
              />
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}

/** Pill button used in the filter toggle. */
function FilterButton({ active, onClick, count, children }) {
  return (
    <button
      onClick={onClick}
      className={`px-2.5 py-1 text-[11px] font-medium rounded-md transition-colors ${
        active
          ? 'bg-orange-500 text-black'
          : 'bg-[#1a1a1a] border border-[#2a2a2a] text-zinc-400 hover:text-white hover:border-[#3a3a3a]'
      }`}
    >
      {children}{' '}
      <span className={active ? 'opacity-70' : 'opacity-50'}>({count})</span>
    </button>
  )
}

/**
 * Single row for one commitment.
 *
 * Click the text to edit it inline. Enter saves, Escape cancels, blur also
 * saves (so clicking elsewhere doesn't lose your changes). Empty text on
 * save reverts to original.
 */
function CommitmentItem({ commitment, onToggle, onDelete, onEdit, onReschedule }) {
  const [editing, setEditing] = useState(false)
  const [editText, setEditText] = useState(commitment.text)
  const [editingTime, setEditingTime] = useState(false)
  const isDone = commitment.status === 'done'
  const dueInfo = formatDueAt(commitment.due_at, isDone)

  function handleTimeChange(localValue) {
    setEditingTime(false)
    if (!localValue) return
    // datetime-local gives a wall-clock string with no zone; interpret it in
    // the browser's timezone and convert to a UTC ISO string for storage.
    const iso = new Date(localValue).toISOString()
    if (onReschedule) onReschedule(iso)
  }

  async function commitEdit() {
    const trimmed = editText.trim()
    // No change or empty → just exit edit mode
    if (!trimmed || trimmed === commitment.text) {
      setEditText(commitment.text)
      setEditing(false)
      return
    }
    await onEdit(trimmed)
    setEditing(false)
  }

  function cancelEdit() {
    setEditText(commitment.text)
    setEditing(false)
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter') {
      e.preventDefault()
      commitEdit()
    } else if (e.key === 'Escape') {
      e.preventDefault()
      cancelEdit()
    }
  }

  function startEditing() {
    if (isDone) return  // don't edit done items
    setEditText(commitment.text)
    setEditing(true)
  }

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
        {editing ? (
          <input
            type="text"
            value={editText}
            onChange={(e) => setEditText(e.target.value)}
            onBlur={commitEdit}
            onKeyDown={handleKeyDown}
            autoFocus
            className="w-full bg-transparent text-sm border-b border-orange-500 focus:outline-none px-0 py-0.5"
          />
        ) : (
          <p
            onClick={startEditing}
            className={`text-sm ${isDone ? 'line-through' : 'cursor-text'}`}
            title={isDone ? '' : 'Click to edit'}
          >
            {commitment.text}
            {commitment.recurrence && commitment.recurrence !== 'none' && (
              <span className="ml-2 inline-flex items-center gap-0.5 align-middle text-[9px] font-semibold uppercase tracking-wider text-orange-300 bg-orange-500/[0.1] border border-orange-500/30 rounded px-1 py-0.5">
                ↻ {commitment.recurrence}
              </span>
            )}
          </p>
        )}
        {/* Due time row — click to reschedule. Open commitments only.
            Shows a datetime-local picker inline; if there's no due time yet,
            offers a "+ set time" affordance. */}
        {editingTime ? (
          <input
            type="datetime-local"
            defaultValue={commitment.due_at ? toLocalInputValue(commitment.due_at) : ''}
            onChange={(e) => handleTimeChange(e.target.value)}
            onBlur={() => setEditingTime(false)}
            autoFocus
            className="mt-1 bg-[#222] border border-orange-500/60 rounded px-1.5 py-0.5 text-[11px] text-zinc-200 focus:outline-none [color-scheme:dark]"
          />
        ) : dueInfo ? (
          <p
            onClick={() => !isDone && setEditingTime(true)}
            className={`text-[11px] mt-0.5 ${isDone ? '' : 'cursor-pointer hover:text-orange-400'} ${
              dueInfo.overdue && !isDone ? 'text-red-400' : 'text-zinc-500'
            }`}
            title={isDone ? '' : 'Click to reschedule'}
          >
            {dueInfo.label}
          </p>
        ) : (
          !isDone && (
            <button
              onClick={() => setEditingTime(true)}
              className="mt-0.5 text-[11px] text-zinc-600 hover:text-orange-400 transition-colors"
            >
              + set time
            </button>
          )
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
 * Convert a stored UTC ISO datetime into the value a <input type="datetime-local">
 * expects: a local-timezone "YYYY-MM-DDTHH:mm" string (no zone suffix).
 */
function toLocalInputValue(iso) {
  const d = new Date(iso)
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/**
 * Format a due_at ISO string for display next to a commitment.
 *
 * Returns:
 *   - null if no due_at
 *   - { label, overdue } where label is a short human string and
 *     overdue is true if the due date has passed (used for styling).
 */
function formatDueAt(dueAt, isDone) {
  if (!dueAt) return null

  const due = new Date(dueAt)
  const now = new Date()
  const overdue = !isDone && due < now

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
