import { useState } from 'react'

/**
 * Small UI element that prompts the user to enable browser notifications,
 * or warns them if they've been blocked.
 *
 * Hidden when permission is 'granted' — the user doesn't need to think
 * about this in the steady state.
 *
 * Browser notification permission has three states:
 *  - 'default' — the user hasn't been asked yet. Show a button to ask.
 *  - 'granted' — notifications work. Show nothing.
 *  - 'denied'  — the user blocked them. Show a note explaining how to fix.
 */
export default function NotificationStatus() {
  const initial =
    typeof Notification !== 'undefined' ? Notification.permission : 'denied'
  const [permission, setPermission] = useState(initial)

  // No Notification API at all (older browsers, some embedded contexts)
  if (typeof Notification === 'undefined') return null

  // Already granted — get out of the user's way
  if (permission === 'granted') return null

  async function requestPermission() {
    const result = await Notification.requestPermission()
    setPermission(result)
  }

  if (permission === 'denied') {
    return (
      <p className="text-[11px] text-zinc-600 mb-3">
        Notifications blocked. Enable them in your browser settings to get
        reminders when commitments come due.
      </p>
    )
  }

  // permission === 'default' — show a button to request
  return (
    <button
      onClick={requestPermission}
      className="text-[11px] text-zinc-500 hover:text-orange-500 transition-colors mb-3 underline underline-offset-2 decoration-zinc-700 hover:decoration-orange-500"
    >
      Enable reminders →
    </button>
  )
}
