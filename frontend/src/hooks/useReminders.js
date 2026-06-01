import { useEffect, useRef, useState } from 'react'
import { getSetting } from '../lib/settings'

/**
 * useReminders — fires browser notifications when commitments become due.
 *
 * Design:
 *   - ONE stable interval per "polling interval" setting. The interval
 *     reads the latest commitments from a ref, so it doesn't reset when
 *     commitments change.
 *
 *   - Polls every pollIntervalMs (configurable via Settings; default 30s).
 *     The interval is recreated when the setting changes.
 *
 *   - On the first check WITH non-empty commitments, items already overdue
 *     get silently marked as notified — avoids a burst when you open the
 *     app with 5 overdue items.
 *
 *   - For each subsequent check, items newly overdue this session fire a
 *     browser notification with requireInteraction (won't auto-dismiss).
 *
 *   - tag: c.id deduplicates — a second notification for the same id
 *     replaces the first instead of stacking.
 */

const DEBUG = true

export function useReminders(commitments) {
  const notifiedIds = useRef(new Set())
  const isFirstCheckWithData = useRef(true)
  const commitmentsRef = useRef(commitments)
  const [pollIntervalMs, setPollIntervalMs] = useState(() => getSetting('pollIntervalMs'))

  // Keep the ref in sync with the latest commitments WITHOUT
  // re-creating the interval.
  useEffect(() => {
    commitmentsRef.current = commitments
  }, [commitments])

  // React to settings changes (e.g., user picks a new poll interval).
  useEffect(() => {
    function handleSettingsChange(e) {
      if (e.detail?.key === 'pollIntervalMs') {
        setPollIntervalMs(e.detail.value)
      }
    }
    window.addEventListener('overwatch-settings-changed', handleSettingsChange)
    return () => window.removeEventListener('overwatch-settings-changed', handleSettingsChange)
  }, [])

  // Set up the polling interval. Recreates when pollIntervalMs changes.
  useEffect(() => {
    if (typeof Notification === 'undefined') {
      if (DEBUG) console.log('[useReminders] Notification API not available')
      return
    }
    if (Notification.permission !== 'granted') {
      if (DEBUG) console.log('[useReminders] permission not granted:', Notification.permission)
      return
    }

    function check() {
      const now = Date.now()
      const current = commitmentsRef.current

      if (DEBUG) {
        console.log(
          `[useReminders] check at ${new Date().toLocaleTimeString()} — ${current.length} commitments, firstCheck=${isFirstCheckWithData.current}`
        )
      }

      if (current.length === 0) {
        return
      }

      for (const c of current) {
        if (c.status !== 'open') continue
        if (!c.due_at) continue
        if (notifiedIds.current.has(c.id)) continue

        const due = new Date(c.due_at).getTime()
        if (due > now) continue

        if (isFirstCheckWithData.current) {
          notifiedIds.current.add(c.id)
          if (DEBUG) console.log(`[useReminders] suppressing first-check overdue: "${c.text}"`)
        } else {
          if (DEBUG) console.log(`[useReminders] firing notification: "${c.text}"`)
          new Notification('Overwatch', {
            body: `You said you'd: ${c.text}`,
            tag: c.id,
            requireInteraction: true,
          })
          notifiedIds.current.add(c.id)
        }
      }
      isFirstCheckWithData.current = false
    }

    check()
    const interval = setInterval(check, pollIntervalMs)
    return () => clearInterval(interval)
  }, [pollIntervalMs])
}
