import { useEffect, useRef } from 'react'

/**
 * useReminders — fires browser notifications when commitments become due.
 *
 * Polls every 60 seconds (and runs once on mount). For each open commitment
 * whose due_at has passed AND we haven't notified about yet, fires a browser
 * Notification. Tracks notified IDs in a ref so we don't re-notify across
 * checks or re-renders.
 *
 * Design choices:
 *
 *  - On first check after mount, items that are ALREADY overdue get silently
 *    marked as notified (no notification fires). Reason: avoid a burst of
 *    notifications when you open the app and have 5 overdue items. The
 *    briefing card + visual list already surface those.
 *
 *  - On subsequent checks, any item that becomes newly overdue fires a
 *    notification. That's the "surgical follow-up" mechanic from the PRD.
 *
 *  - requireInteraction: true keeps the notification until you click it,
 *    rather than auto-dismissing after a few seconds. Commitments deserve
 *    attention.
 *
 *  - tag: c.id deduplicates — if the same id somehow gets two notifications,
 *    the second replaces the first instead of stacking.
 *
 * Silently does nothing if Notification API is unavailable or permission
 * is not granted.
 */
export function useReminders(commitments) {
  const notifiedIds = useRef(new Set())
  const isFirstCheck = useRef(true)

  useEffect(() => {
    if (typeof Notification === 'undefined') return
    if (Notification.permission !== 'granted') return

    function check() {
      const now = Date.now()
      for (const c of commitments) {
        if (c.status !== 'open') continue
        if (!c.due_at) continue
        if (notifiedIds.current.has(c.id)) continue

        const due = new Date(c.due_at).getTime()
        if (due > now) continue

        // Newly overdue this session
        if (isFirstCheck.current) {
          // Suppress notifications for items already overdue at mount —
          // the user sees them visually and via the briefing.
          notifiedIds.current.add(c.id)
        } else {
          new Notification('Overwatch', {
            body: `You said you'd: ${c.text}`,
            tag: c.id,
            requireInteraction: true,
          })
          notifiedIds.current.add(c.id)
        }
      }
      isFirstCheck.current = false
    }

    check()
    const interval = setInterval(check, 60 * 1000)
    return () => clearInterval(interval)
  }, [commitments])
}
