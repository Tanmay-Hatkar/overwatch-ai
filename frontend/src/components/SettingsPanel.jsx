import { useState, useEffect } from 'react'
import { toast } from 'sonner'
import { getSetting, setSetting, POLL_INTERVAL_PRESETS } from '../lib/settings'
import { sendTestNotification, notificationsAreNative } from '../lib/notifications'
import { isProactiveVoiceEnabled, setProactiveVoiceEnabled } from '../lib/proactiveVoice'

/**
 * SettingsPanel — modal-ish overlay with user preferences.
 *
 * Opens from a gear icon in the header. Click outside or the close button
 * to dismiss. Settings persist to localStorage immediately on change;
 * components that care subscribe via the 'overwatch-settings-changed' event.
 */
export default function SettingsPanel({ open, onClose }) {
  const [pollIntervalMs, setPollIntervalMs] = useState(() => getSetting('pollIntervalMs'))
  const [permission, setPermission] = useState(
    typeof Notification !== 'undefined' ? Notification.permission : 'unsupported',
  )
  const [proactiveVoice, setProactiveVoice] = useState(() => isProactiveVoiceEnabled())

  function toggleProactiveVoice() {
    const next = !proactiveVoice
    setProactiveVoice(next)
    setProactiveVoiceEnabled(next)
  }

  async function handleTestReminder() {
    const msg = await sendTestNotification()
    toast.message(msg)
  }

  // Re-read permission state whenever the panel opens (in case the user
  // toggled it elsewhere).
  useEffect(() => {
    if (open && typeof Notification !== 'undefined') {
      setPermission(Notification.permission)
    }
  }, [open])

  if (!open) return null

  function handleIntervalChange(e) {
    const value = parseInt(e.target.value, 10)
    setPollIntervalMs(value)
    setSetting('pollIntervalMs', value)
  }

  async function requestNotificationPermission() {
    if (typeof Notification === 'undefined') return
    const result = await Notification.requestPermission()
    setPermission(result)
  }

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40"
        onClick={onClose}
      />

      {/* Panel */}
      <div
        className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 w-[90%] max-w-md bg-[#141414] border border-[#2a2a2a] rounded-2xl p-6 shadow-2xl"
        role="dialog"
        aria-labelledby="settings-title"
      >
        <div className="flex items-center justify-between mb-6">
          <h2 id="settings-title" className="text-lg font-bold text-orange-500">
            Settings
          </h2>
          <button
            onClick={onClose}
            className="text-zinc-500 hover:text-white text-2xl leading-none transition-colors"
            aria-label="Close settings"
          >
            ×
          </button>
        </div>

        <div className="space-y-6">
          {/* Notifications */}
          <section>
            <h3 className="text-[10px] font-semibold tracking-[0.15em] uppercase text-zinc-600 mb-2">
              Notifications
            </h3>
            <PermissionStatus
              permission={permission}
              onRequest={requestNotificationPermission}
            />
            <button
              onClick={handleTestReminder}
              className="mt-3 w-full px-4 py-2 bg-[#1a1a1a] border border-[#2a2a2a] hover:border-orange-500/50 text-zinc-200 rounded-lg text-sm transition-colors"
            >
              Send a test reminder (~8s)
            </button>
            <p className="text-xs text-zinc-600 mt-2">
              {notificationsAreNative()
                ? 'Fires an on-device alarm in 8 seconds — lock your phone to confirm it works in the background.'
                : 'On-device alarms only run in the installed Android app. In the browser, reminders use web push.'}
            </p>
          </section>

          {/* Proactive voice */}
          <section>
            <h3 className="text-[10px] font-semibold tracking-[0.15em] uppercase text-zinc-600 mb-2">
              Proactive voice
            </h3>
            <button
              onClick={toggleProactiveVoice}
              className={`w-full flex items-center justify-between px-4 py-2 rounded-lg text-sm transition-colors border ${
                proactiveVoice
                  ? 'bg-orange-500/[0.08] border-orange-500/40 text-orange-200'
                  : 'bg-[#1a1a1a] border-[#2a2a2a] text-zinc-300 hover:border-[#3a3a3a]'
              }`}
            >
              <span>Speak my pending items when I open the app</span>
              <span className="text-xs font-semibold uppercase tracking-wider">
                {proactiveVoice ? 'On' : 'Off'}
              </span>
            </button>
            <p className="text-xs text-zinc-600 mt-2">
              When on, Overwatch greets you out loud with what's overdue and
              what's next.
            </p>
          </section>

          {/* Polling interval */}
          <section>
            <h3 className="text-[10px] font-semibold tracking-[0.15em] uppercase text-zinc-600 mb-2">
              Check for overdue every
            </h3>
            <select
              value={pollIntervalMs}
              onChange={handleIntervalChange}
              className="w-full px-3 py-2 bg-[#1a1a1a] border border-[#2a2a2a] rounded-lg text-[#f5f5f5] text-sm focus:outline-none focus:border-orange-500 transition-colors [color-scheme:dark]"
            >
              {POLL_INTERVAL_PRESETS.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </select>
            <p className="text-xs text-zinc-600 mt-2">
              How often the app checks for newly-overdue commitments. Shorter =
              quicker notifications, slightly more CPU.
            </p>
          </section>

          {/* Install hint */}
          <section>
            <h3 className="text-[10px] font-semibold tracking-[0.15em] uppercase text-zinc-600 mb-2">
              Install as app
            </h3>
            <p className="text-sm text-zinc-300">
              Look for the install icon in your browser's URL bar
              <span className="text-zinc-500"> (Chrome/Edge desktop)</span> or
              "Add to Home Screen"
              <span className="text-zinc-500"> (mobile)</span>.
            </p>
            <p className="text-xs text-zinc-600 mt-2">
              Installed, the app opens full-screen with its own icon — no browser
              chrome.
            </p>
          </section>
        </div>
      </div>
    </>
  )
}

function PermissionStatus({ permission, onRequest }) {
  if (permission === 'unsupported') {
    return (
      <p className="text-sm text-zinc-500">
        Browser does not support notifications.
      </p>
    )
  }
  if (permission === 'granted') {
    return (
      <p className="text-sm text-emerald-400">
        ✓ Enabled. You'll get a notification when a commitment becomes due.
      </p>
    )
  }
  if (permission === 'denied') {
    return (
      <p className="text-sm text-red-400">
        Blocked. Click the lock icon in your browser's URL bar to re-enable.
      </p>
    )
  }
  return (
    <button
      onClick={onRequest}
      className="px-4 py-2 bg-orange-500 hover:bg-orange-600 text-black font-semibold rounded-lg text-sm transition-colors"
    >
      Enable notifications
    </button>
  )
}
