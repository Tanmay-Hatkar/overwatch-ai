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
 *
 * No grouping and no due-time editing from here (ADR-0023) — both are
 * list-management ceremony that bypassed the chat capture/modify channel.
 * If a commitment's time needs to change, say so in chat.
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

  async function handleEdit(commitment, changes) {
    try {
      await updateCommitment(commitment.id, changes)
      onChange()
    } catch (err) {
      toast.error(err.message || "Couldn't save edit.")
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
                onEdit={(changes) => handleEdit(c, changes)}
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
                onEdit={(changes) => handleEdit(c, changes)}
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
 * Click the text to edit it inline — this also reveals a second field for
 * reminder_phrase (the line spoken/shown at reminder time, ADR-0021's "You
 * said you'd..." recall). Enter saves, Escape cancels, blur also saves
 * (tracked at the container level so tabbing between the two fields
 * doesn't save prematurely — only losing focus entirely does). Empty text
 * on save reverts to original; an emptied reminder_phrase clears it back
 * to null (falls back to the templated reminder text).
 */
function CommitmentItem({ commitment, onToggle, onDelete, onEdit }) {
  const [editing, setEditing] = useState(false)
  const [editText, setEditText] = useState(commitment.text)
  const [editPhrase, setEditPhrase] = useState(commitment.reminder_phrase || '')
  const isDone = commitment.status === 'done'
  const dueInfo = formatDueAt(commitment.due_at, isDone)

  async function commitEdit() {
    const trimmedText = editText.trim()
    const trimmedPhrase = editPhrase.trim()
    const changes = {}
    if (trimmedText && trimmedText !== commitment.text) changes.text = trimmedText
    if (trimmedPhrase !== (commitment.reminder_phrase || '')) {
      changes.reminder_phrase = trimmedPhrase || null
    }

    if (Object.keys(changes).length === 0) {
      setEditText(commitment.text)
      setEditPhrase(commitment.reminder_phrase || '')
      setEditing(false)
      return
    }
    await onEdit(changes)
    setEditing(false)
  }

  function cancelEdit() {
    setEditText(commitment.text)
    setEditPhrase(commitment.reminder_phrase || '')
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

  function handleGroupBlur(e) {
    // Only commit when focus leaves BOTH fields, not when tabbing from
    // text to reminder_phrase (relatedTarget stays inside the container).
    if (!e.currentTarget.contains(e.relatedTarget)) {
      commitEdit()
    }
  }

  function startEditing() {
    if (isDone) return  // don't edit done items
    setEditText(commitment.text)
    setEditPhrase(commitment.reminder_phrase || '')
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
          <div onBlur={handleGroupBlur}>
            <input
              type="text"
              value={editText}
              onChange={(e) => setEditText(e.target.value)}
              onKeyDown={handleKeyDown}
              autoFocus
              className="w-full bg-transparent text-sm border-b border-orange-500 focus:outline-none px-0 py-0.5"
            />
            <div className="mt-1.5">
              <label className="block text-[9px] uppercase tracking-wider text-zinc-600 mb-0.5">
                How I'll remind you
              </label>
              <input
                type="text"
                value={editPhrase}
                onChange={(e) => setEditPhrase(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="e.g. You said you'd call mom at 3pm — calling now?"
                maxLength={200}
                className="w-full bg-transparent text-xs text-zinc-400 border-b border-[#3a3a3a] focus:border-orange-500 focus:outline-none px-0 py-0.5"
              />
            </div>
          </div>
        ) : (
          <>
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
            {commitment.reminder_phrase && (
              <p
                onClick={startEditing}
                className="text-[10px] mt-0.5 text-zinc-600 italic truncate cursor-text"
                title={`Click to edit: ${commitment.reminder_phrase}`}
              >
                🔔 “{commitment.reminder_phrase}”
              </p>
            )}
          </>
        )}
        {/* Due time row — read-only. To change a commitment's time, say so
            in chat (ADR-0023: no inline reschedule UI). */}
        {dueInfo && (
          <p className="text-[11px] mt-0.5 flex items-center gap-2 flex-wrap">
            <span className={dueInfo.overdue && !isDone ? 'text-red-400' : 'text-zinc-500'}>
              {dueInfo.label}
            </span>
            {/* Lead-time badge — the reminder shown as a sub-detail of the
                commitment (Todoist/TickTick style), not a separate item. */}
            {commitment.reminder_lead_minutes > 0 && (
              <span className="inline-flex items-center gap-0.5 text-[9px] font-semibold uppercase tracking-wider text-emerald-300 bg-emerald-500/[0.08] border border-emerald-500/25 rounded px-1 py-0.5">
                🔔 {formatLead(commitment.reminder_lead_minutes)} before
              </span>
            )}
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

/** Humanize a lead time for the 🔔 badge ("15 min", "1 hr", "2 hr"). */
function formatLead(minutes) {
  if (minutes >= 60 && minutes % 60 === 0) return `${minutes / 60} hr`
  return `${minutes} min`
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
